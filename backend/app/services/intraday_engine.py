import asyncio
import pandas as pd
import numpy as np
import random
import time
from app.services.market_data import market_service
from app.services.index_context import index_ctx
from app.services.liquidity_service import liquidity_service
from app.services.kite_service import kite_service
import app.services.ta_intraday as ta_intraday
from app.services.utils import STATIC_FULL_LIST, sanitize_data
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
import pytz
from datetime import datetime, timedelta
from app.core.config import settings
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange

def safe_scalar(x):
    if x is None: return 0.0
    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)
    return float(np.nan_to_num(val, nan=0.0))

class IntradayEngine:
    """
    [V11 RESTORED] Ultra-Sync Institutional Engine.
    Restores the full 12-point Audit Grid with V10 Pulse Concurrency (2200+ Symbols).
    """

    def __init__(self):
        # 🛰️ Pulse-Fire Concurrency
        self.semaphore = asyncio.Semaphore(50) 
        self.job_states = {}
        
        # [V13] CENTRALIZED INSTITUTIONAL CONFIG
        self.CONFIG = {
            "version": "V13-PIONEER",
            "rvol_threshold": 2.5,
            "decay_factor": 15,
            "bias_cap": 25,
            "max_gate_atr": 0.8,
            "min_gate_atr": 0.3,
            "score_floor": 65,
            "top_n_cap": 50,
            "ers_reject_normal": 60,
            "ers_reject_trend": 55,
            "ers_degrade_normal": 75,
            "ers_degrade_trend": 70,
            "unlock_threshold": 3
        }

        # [V13] SYSTEM STATE CONTROLLER
        self.system_state = {
            "regime": "Mixed",
            "regime_strength": "NORMAL",
            "regime_weight": 1.0,
            "risk_mode": "Normal",
            "freeze_mode": False,
            "inflation_rate": 0.0,
            "stable_scans_count": 0,
            "health_score": 100,
            "tighten_level": 0,
            "last_regime_change": datetime.utcnow()
        }

        # [V13] PERFORMANCE METRICS (TIME-SEGMENTED)
        self.performance_metrics = {
            "morning": {"avg_score": 0, "total_signals": 0, "inflation_rate": 0},
            "midday": {"avg_score": 0, "total_signals": 0, "inflation_rate": 0},
            "eod": {"avg_score": 0, "total_signals": 0, "inflation_rate": 0},
            "raw_score_max_seen": 0,
            "scores_above_80": 0
        }

        self.persistence_cache = {} # Cross-scan memory
        self.execution_profile = {} # Slippage feedback loop

    async def _get_index_context(self):
        """[V13] Elite Market Regime & State Synchronization."""
        try:
            # 1. FETCH NIFTY DATA
            nifty_df = await market_service.get_ohlc("^NSEI", period="2d", interval="5m")
            if nifty_df is None or nifty_df.empty: 
                return self.system_state
            
            close = nifty_df['close'].iloc[-1]
            vwap = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap(nifty_df)
            ad_ratio = await market_service.get_advance_decline_ratio()
            
            # [V14] FETCH INDIA VIX
            market_status = await market_service.get_market_status()
            india_vix = market_status.get("india_vix", 15.0)

            # 2. ADX STABILITY (3-Candle Check)
            adx_series = ta_intraday.ADXIndicator(high=nifty_df['high'], low=nifty_df['low'], close=nifty_df['close']).adx()
            curr_adx = adx_series.iloc[-1]
            prev_adx_avg = adx_series.iloc[-3:].mean()
            
            # 3. REGIME DETECTION WITH HYSTERESIS
            prev_regime = self.system_state.get("regime", "Mixed")
            day_ret = (close - nifty_df['open'].iloc[0]) / nifty_df['open'].iloc[0]
            
            regime = prev_regime
            if prev_regime == "Trend":
                if curr_adx < 18 and abs(day_ret) < 0.002: regime = "Range"
            else: # Range or Mixed
                if curr_adx > 25 or abs(day_ret) > 0.004: regime = "Trend"

            # 4. REGIME STRENGTH & WEIGHTING [V18 FIX #1: Was dead code — now reachable]
            strength = "NORMAL"
            weight = 1.0
            if regime == "Trend":
                if curr_adx > 30: 
                    strength = "STRONG_TREND"; weight = 1.15
                else: 
                    strength = "WEAK_TREND"; weight = 1.05
            else:
                if curr_adx < 20: 
                    strength = "CHOP"; weight = 0.85
                    
            # 5. SYNC SYSTEM STATE
            self.system_state.update({
                "regime": regime,
                "regime_strength": strength,
                "regime_weight": weight,
                "day_change_pct": round(day_ret * 100, 2),
                "ad_ratio": ad_ratio,
                "nifty_close": close,
                "nifty_vwap": vwap,
                "india_vix": india_vix
            })
            
            return {
                "day_change_pct": round(day_ret * 100, 2),
                "india_vix": india_vix,
                "regime": regime,
                "regime_strength": strength,
                "regime_weight": weight,
                "15m_returns": nifty_df['close'].pct_change().dropna(),
                "vwap": vwap,
                "close": close,
                "ad_ratio": ad_ratio
            }
        except Exception as e:
            print(f"Index Context Error: {e}")
            return self.system_state

    def _get_adaptive_ers_threshold(self) -> dict:
        """[V14] Dynamic ERS Gating based on VIX and Regime."""
        regime = self.system_state.get("regime", "Mixed")
        vix = self.system_state.get("india_vix", 15.0)
        
        # Volatility Multiplier: As VIX rises, we tighten the gate (high slippage risk)
        # Base VIX assumed at 15.0. 
        # If VIX=20, mult = 1.0 + (20-15)/50 = 1.1
        vix_mult = 1.0 + max(0, (vix - 15.0) / 50.0)
        
        is_trend = regime == "Trend" or self.system_state.get("regime_strength") == "STRONG_TREND"
        
        base_reject = self.CONFIG["ers_reject_trend"] if is_trend else self.CONFIG["ers_reject_normal"]
        base_degrade = self.CONFIG["ers_degrade_trend"] if is_trend else self.CONFIG["ers_degrade_normal"]
        
        return {
            "reject": round(base_reject * vix_mult, 1),
            "degrade": round(base_degrade * vix_mult, 1)
        }

    async def _calculate_sector_heat(self, batch_pulse: dict):
        """[V14] Industry Standard Sector Momentum Booster."""
        sector_rets = {}
        sector_counts = {}
        
        for sym, data in batch_pulse.items():
            if not data or data.get("price", 0) == 0: continue
            df = data.get("15m")
            if df is None or df.empty: continue
            
            sector = market_service.get_sector_for_symbol(sym)
            if sector == "General": continue
            
            # Safe access to Day Open (9:15 candle)
            try:
                if 'open' in df.columns:
                    day_open = float(df['open'].iloc[0])
                else:
                    day_open = float(df.iloc[0, 0]) # Fallback to first column
                
                if day_open > 0:
                    ret = (data["price"] - day_open) / day_open
                    sector_rets[sector] = sector_rets.get(sector, 0.0) + ret
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1
            except:
                continue
            
        heat = {}
        for sector, total_ret in sector_rets.items():
            avg_ret = total_ret / sector_counts[sector]
            heat[sector] = avg_ret
            
        return heat

    def report_execution_outcome(self, symbol: str, status: str, slippage_pct: float = 0.0):
        """[V13] Execution Feedback Loop Infrastructure."""
        if symbol not in self.execution_profile:
            self.execution_profile[symbol] = {"success_count": 0, "fail_count": 0, "avg_slippage": 0.0}
        
        prof = self.execution_profile[symbol]
        if status == "SUCCESS":
            prof["success_count"] += 1
            # Rolling average slippage
            prof["avg_slippage"] = (prof["avg_slippage"] * (prof["success_count"] - 1) + slippage_pct) / prof["success_count"]
        else:
            prof["fail_count"] += 1

    def _calculate_priority_score(self, base_score: float, indicators: dict, sym: str, persistence: int = 0) -> float:
        """[V14] Explicit Institutional Priority Equation with Sigmoid Footprint."""
        # 1. BASE FACTORS
        conf_weight = 1.0
        if base_score >= 85: conf_weight = 1.2
        elif base_score < 70: conf_weight = 0.8
        
        regime_weight = self.system_state.get("regime_weight", 1.0)
        
        # 2. EXECUTION & PERSISTENCE
        ers_score = indicators.get("ers_score", 100)
        ers_weight = 1.0
        
        # [V14] Adaptive ERS Gating
        ers_gates = self._get_adaptive_ers_threshold()
        if ers_score < ers_gates["degrade"]: 
            ers_weight = 0.8
        
        # [V14] PERSISTENCE FOOTPRINT (Centered Sigmoid)
        # raw_footprint = persistence * rvol
        # We use standard mean=5.0, std_dev=3.0 for institutional normalization
        rvol = indicators.get("rvol", 1.0)
        footprint_weight = ta_intraday.IntradayTechnicalAnalysis.calculate_institutional_footprint(
            persistence, rvol, mean_fp=3.0, std_fp=2.0
        )
        # Scale footprint from (0,1) to (0.9, 1.2) range for priority impact
        persistence_weight = 0.9 + (footprint_weight * 0.3)
            
        # Cooldown Penalty
        cooldown_weight = 1.0
        last_trade_time = indicators.get("last_trade_time") # Placeholder for execution sync
        if last_trade_time:
            cooldown_weight = 0.85 if self.system_state.get("regime_strength") == "STRONG_TREND" else 0.7
            
        # 3. FINAL EQUATION [V14 APEX]
        base_priority = base_score * conf_weight * regime_weight * ers_weight * persistence_weight * cooldown_weight
        
        # [V14] DETERMINISTIC TIE-BREAKER (Industry Standard)
        # We add 0.01% of RVOL to the priority. At identical base scores, 
        # the stock with higher relative institutional participation wins the rank.
        tie_breaker = min(rvol, 10.0) / 1000.0 
        
        priority = base_priority + tie_breaker
            
        # Clamp to 100 for consistency
        return round(min(priority, 100), 3)

    def _sync_scans_and_risk(self, signals: list):
        """[V13] System State State-Machine Update."""
        if not signals: return
        
        avg_score = sum(s["score"] for s in signals) / len(signals)
        high_quality = [s for s in signals if s["score"] >= 80]
        inflation_rate = len(high_quality) / len(signals) if signals else 0
        
        # Update segmented metrics based on current time
        ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
        hour = ist_now.hour + ist_now.minute/60.0
        segment = "morning" if hour < 11.5 else ("midday" if hour < 14.0 else "eod")
        
        self.performance_metrics[segment].update({
            "avg_score": avg_score,
            "total_signals": len(signals),
            "inflation_rate": inflation_rate
        })
        
        # Risk Mode Logic (Gradual Degradation)
        risk_mode = "Normal"
        if inflation_rate > 0.4:
            risk_mode = "Restricted" # Over-saturated / Noisy
            self.system_state["tighten_level"] = 1
        elif avg_score < 50 and self.system_state["regime_strength"] == "CHOP":
            risk_mode = "Stop" # Capital Preservation
            
        # Adaptation Recover (Un-Freeze)
        if inflation_rate < 0.2:
            self.system_state["stable_scans_count"] += 1
            if self.system_state["stable_scans_count"] >= self.CONFIG["unlock_threshold"]:
                self.system_state["freeze_mode"] = False
                self.system_state["tighten_level"] = 0
        else:
            self.system_state["stable_scans_count"] = 0

        self.system_state.update({
            "inflation_rate": inflation_rate,
            "risk_mode": risk_mode,
            "health_score": round(avg_score * (1 - inflation_rate), 2)
        })

    async def analyze_stock(self, sym: str, job_id: str = None, global_index_ctx: dict = None, pulse_data: dict = None, sector_heat: dict = None):
        """[V14] Final 10/10 Institutional Analysis Pipeline (L1-L3)."""
        try:
            # [V18 FIX #13] Null guard for index context
            global_index_ctx = global_index_ctx or {}
            regime = global_index_ctx.get("regime", "Mixed")
            # 1. DATA EXTRACTION & L1 DETECTION
            df_15m = None; df_1h = None; df_1d = None; real_price = 0.0
            if pulse_data and sym in pulse_data:
                item = pulse_data[sym]
                if isinstance(item, pd.DataFrame): df_15m = item
                elif isinstance(item, dict):
                    df_15m = item.get("15m"); df_1h = item.get("1h")
                if df_15m is not None and not df_15m.empty:
                    real_price = float(df_15m['close'].iloc[-1])
            else:
                df_15m = await market_service.get_ohlc(sym, period="7d", interval="15m")
                pinfo = await market_service.get_live_price(sym)
                real_price = pinfo.get("price", 0.0)

            if df_15m is None or df_15m.empty or len(df_15m) < 20:
                return {"symbol": sym, "skip_reason": "Data Failure"}

            # INDICATOR INTEGRITY GUARD
            indicators = self._get_indicators(df_15m, df_1h)
            # [V18 FIX #8] Null guard for indicators
            if indicators is None:
                return {"symbol": sym, "skip_reason": "Indicator Computation Failed"}
            guard = ta_intraday.IntradayTechnicalAnalysis.indicator_integrity_guard(df_15m, indicators)
            if guard["status"] == "safe_skip":
                return {"symbol": sym, "skip_reason": guard["reason"]}

            # PATTERN DETECTION (L1)
            patterns = ta_intraday.IntradayTechnicalAnalysis.detect_pullback_entry_v45(df_15m, indicators['ema20'], context=global_index_ctx)
            
            # --- L2: SCORING ENGINE ---
            l1_score, l1_data = self._run_layer1(indicators)
            l2_score, l2_data = self._run_layer2(indicators, df_15m)
            
            # [V17] Beta-Adjusted RS Alpha (Stock vs Index)
            index_rets = global_index_ctx.get("15m_returns", pd.Series())
            stock_rets = df_15m['close'].pct_change().dropna()
            rs_alpha = ta_intraday.IntradayTechnicalAnalysis.calculate_relative_strength_alpha(stock_rets, index_rets)
            
            # [V18 FIX #15] Single RS contribution — no double counting
            rs_contribution = max(min(rs_alpha * 1000, 15), -15)
            
            # [V19 APEX-A] MULTI-TIMEFRAME CONFLUENCE GATE
            mtf_bonus = 0
            if indicators.get("ema_1h_trend_up"):
                mtf_bonus += 5  # 1h trend supports 15m setup
            else:
                mtf_bonus -= 10  # Counter-trend penalty: 15m bullish but 1h bearish
            # Triple alignment bonus (15m + 1h + 1d all bullish)
            if indicators.get("ema_1h_trend_up") and indicators.get("is_1d_bullish"):
                mtf_bonus += 5  # Full alignment = highest conviction
            
            # [V17] SECTOR HEAT GATING (Structural Filter)
            sector_boost = 0
            sector = market_service.get_sector_for_symbol(sym)
            heat = 0.0
            if sector_heat:
                heat = sector_heat.get(sector, 0.0)
                # Hard rejection if sector is crashing
                if heat < -0.005:
                    return {"symbol": sym, "skip_reason": f"Negative Sector Heat ({heat*100:.2f}%)"}
                if heat > 0:
                    # Scale boost: 5 pts for 0.5% heat, max 10 pts
                    sector_boost = min(10, heat * 1000)
            
            # [V19 APEX-F] SECTOR ROTATION ALPHA
            # Stock outperforming a hot sector = institutional rotation play
            rotation_boost = 0
            if rs_alpha > 0.002 and heat > 0.005:
                rotation_boost = min(8, heat * 800)  # +4 for 0.5% heat, +8 for 1%+
            
            base_score = max(0, min(100, l1_score + l2_score + rs_contribution + mtf_bonus + sector_boost + rotation_boost))
            
            # [V18 FIX #7] L3: PENALTY ENGINE — re-integrated into scoring
            liq = liquidity_service.get_liquidity(sym)
            l3_penalty, l3_data = self._run_layer3(indicators, df_15m, global_index_ctx, l2_data, liq)
            base_score = max(0, min(100, base_score - l3_penalty))
            
            # --- L3: EXECUTION GATING ---
            # 1. Freshness Guard
            now = datetime.utcnow()
            last_candle_time = df_15m.index[-1].to_pydatetime().replace(tzinfo=None)
            if (now - last_candle_time).total_seconds() > 600: # 10m limit
                return {"symbol": sym, "skip_reason": "Stale Data (>10m)"}
            
            # 2. Volatility Kill-Switch
            atr_pct = indicators['atr'] / real_price
            if atr_pct > 0.05: # Extreme volatility reject
                return {"symbol": sym, "skip_reason": "Extreme Volatility (ATR > 5%)"}
            
            # [V14] 3. Multi-Day Weekly Resistance Hard Filter
            # Automatically reject Longs if price is within 0.5% of 5-Day High
            df_1d = pulse_data.get(sym, {}).get("1d") if pulse_data else None
            if df_1d is not None and not df_1d.empty and len(df_1d) >= 5:
                weekly_high = float(df_1d['high'].tail(5).max())
                # If we are within 0.3% of the weekly high, the risk of a distribution trap is huge
                if real_price >= weekly_high * 0.997 and real_price < weekly_high * 1.002:
                    return {"symbol": sym, "skip_reason": "Multi-Day Resistance (Near 5D High)"}
                
                # [V17] 3b. Macro-Alignment Hard Gate (Daily EMA-20)
                # Hard rejection if trading against primary daily trend
                ema20_1d = EMAIndicator(close=df_1d['close'], window=20).ema_indicator().iloc[-1]
                if real_price < ema20_1d:
                    return {"symbol": sym, "skip_reason": "Against Macro Trend (Price < 1D EMA-20)"}
                
                # [V18 FIX #14] Inject is_1d_bullish from actual 1D data for L3 penalties
                indicators["is_1d_bullish"] = real_price > ema20_1d
            else:
                indicators["is_1d_bullish"] = True  # Default bullish if no daily data
                
            # 4. ERS Terminal Gating
            ers_score = indicators.get("ers_score", 100)
            ers_gates = self._get_adaptive_ers_threshold()
            if ers_score < ers_gates["reject"]:
                return {"symbol": sym, "skip_reason": f"Adaptive ERS Reject ({ers_score} < {ers_gates['reject']})"}
            
            # 4. VWAP Soft Penalty
            vwap_dist = abs(real_price - indicators['vwap_val']) / max(indicators['atr'], 1e-6)
            if vwap_dist > 1.5:
                base_score *= 0.8 # Anti-chase penalty
                
            # 5. 9:30 Trap
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            if ist_now.hour == 9 and ist_now.minute < 30:
                # Require 'Open Drive' confirmation or high-velocity reclaim
                if not patterns.get("hv_reclaim") and patterns.get("expansion_ratio", 0) < 1.0:
                    return {"symbol": sym, "skip_reason": "9:30 Trap Guard"}

            # --- PRIORITY CALCULATION ---
            indicators["ers_score"] = ers_score
            scan_history = self.persistence_cache.get(sym, [])
            persistence_count = sum(1 for s in scan_history if s.get("score", 0) >= 70)
            
            # [V19 APEX-E] MOMENTUM PERSISTENCE BOOST
            # Stocks in 3+ consecutive scans with score >= 70 = accumulating institutional interest
            persistence_boost = 0
            if persistence_count >= 3:
                persistence_boost = min(8, persistence_count * 2)  # 3→6, 4→8, cap 8
                base_score = min(100, base_score + persistence_boost)
            
            priority = self._calculate_priority_score(base_score, indicators, sym, persistence=persistence_count)

            # [V18 FIX #2] Dead code block removed — Build Final Institutional Output
            # [V18 FIX #7] Incorporate L3 into output for transparency
            adv20 = liq.get("adv20", 0)
            liq_level = liq.get("level", "Unknown")
            max_qty = int(adv20 * 0.01) if adv20 > 0 else 0
            max_value = round(max_qty * real_price, 0)

            # Build reasons list for UI transparency
            reasons = []
            for r_obj in l1_data.get("reasons", []):
                reasons.append({"text": r_obj["text"], "type": "positive", "layer": 1, "impact": r_obj["impact"]})
            for r_obj in l2_data.get("reasons", []):
                reasons.append({"text": r_obj["text"], "type": "positive", "layer": 2, "impact": r_obj["impact"]})
            for r_obj in l3_data.get("reasons", []):
                reasons.append({"text": r_obj["text"], "type": "negative", "layer": 3, "impact": r_obj["impact"]})

            groups = {
                "DNA (40%)": {"score": l1_score, "max": 40, "details": [r for r in reasons if r["layer"] == 1]},
                "Alpha Edge (60%)": {"score": l2_score, "max": 60, "details": [r for r in reasons if r["layer"] == 2]},
                "Safeguards (L3)": {"score": -l3_penalty, "max": 0, "details": [r for r in reasons if r["layer"] == 3]}
            }

            signal = self._get_signal(base_score)
            verdict = "PIONEER PRIME" if base_score >= 85 else "Standard"

            # [V19 APEX-H] STRUCTURAL RISK MANAGEMENT
            india_vix = global_index_ctx.get("india_vix", 15)
            atr = indicators.get("atr", 0)
            
            # Stop-Loss: Tighter of (ATR-based, Structural Swing Low)
            atr_sl = round(real_price - max(atr * (2.0 if india_vix > 20 else 1.5), real_price * 0.005), 2)
            if df_15m is not None and len(df_15m) >= 6:
                structural_sl = round(float(df_15m['low'].iloc[-6:].min()), 2)
                stop_loss = max(structural_sl, atr_sl)  # Higher = tighter for longs
            else:
                stop_loss = atr_sl
            stop_loss = l2_data.get("dynamic_zones", {}).get("stop_loss") or stop_loss
            
            # Target: Nearest resistance level, capped by ATR extension
            atr_target = round(real_price + max(atr * (3.0 if india_vix > 20 else 2.0), real_price * 0.01), 2)
            # Use pivot data if available for realistic resistance targeting
            pivot_data = indicators.get("pivots", {})
            valid_res = [v for v in pivot_data.values() if isinstance(v, (int, float)) and v > real_price * 1.002]
            if valid_res:
                nearest_res = min(valid_res)
                # Use nearest resistance if it's reasonable (at least 0.5% above entry)
                if nearest_res > real_price * 1.005:
                    target = round(min(nearest_res, atr_target * 1.2), 2)  # Cap at 120% of ATR target
                else:
                    target = atr_target
            else:
                target = atr_target
            target = l2_data.get("dynamic_zones", {}).get("target") or target
            
            sl_dist = max(abs(real_price - stop_loss), 0.01)
            
            # [V20 VANGUARD] BETA-NORMALIZED RISK SIZING
            # 1. Base conviction risk
            if base_score >= 85: risk_pct = 0.015
            elif base_score >= 75: risk_pct = 0.012
            else: risk_pct = 0.01
            
            # 2. Normalize risk by the stock's volume/ATR relative to index baseline
            stock_vol = (atr / max(real_price, 1))
            index_vol = 0.005 # Baseline 0.5% 15m vol
            beta_proxy = stock_vol / max(index_vol, 0.001)
            beta_proxy = max(0.5, min(beta_proxy, 2.5)) # Cap between 0.5x and 2.5x
            
            risk_amount = (100000 * risk_pct) / beta_proxy  # ₹1L baseline capital

            return {
                "symbol": sym,
                "price": round(real_price, 2),
                "score": round(base_score, 1),
                "priority": priority,
                "rs_alpha": round(rs_alpha, 4),
                "regime": regime,
                "mode": l2_data.get("mode", "NONE"),
                "flags": {
                    "HV_RECLAIM": patterns.get("hv_reclaim", False),
                    "SQUEEZE": patterns.get("squeeze_detected", False),
                    "STOP_HUNT": patterns.get("stop_hunt_reversal", False),
                    "VACUUM": patterns.get("liquidity_vacuum", False),
                    "FOOTPRINT": indicators.get("footprint", 0),
                    "MTF_ALIGNED": indicators.get("ema_1h_trend_up", False) and indicators.get("is_1d_bullish", False),
                    "PERSISTENCE": persistence_count
                },
                "verdict": verdict,
                "signal": signal,
                "reasons": reasons,
                "groups": groups,
                "entry": round(real_price, 2),
                "target": target,
                "stop_loss": stop_loss,
                "rr_ratio": round((target - real_price) / sl_dist, 2) if sl_dist > 0 else 0,
                "position_size": min(
                    int(risk_amount / sl_dist),
                    int(100000 / max(real_price, 1)),
                    max(int(adv20 * 0.01), 1) if adv20 > 0 else int(100000 / max(real_price, 1))
                ),
                "alpha_mode": l2_data.get("mode", "NONE"),
                "liquidity": {
                    "level": liq_level,
                    "adv20": adv20,
                    "max_stealth_buy_qty": max_qty,
                    "max_stealth_buy_value": max_value
                },
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {"symbol": sym, "skip_reason": f"System Error: {str(e)}"}

    def _get_indicators(self, df_15m, df_1h):
        ind_15m = self._compute_indicators(df_15m)
        if ind_15m is None: return None
        
        try:
            ema_1h_series = EMAIndicator(close=df_1h['close'], window=20).ema_indicator()
            # Safety: Ensure at least two candles for trend comparison
            if len(ema_1h_series) >= 2:
                ema_1h = ema_1h_series.iloc[-1]
                ema_1h_prev = ema_1h_series.iloc[-2]
                ema_1h_trend_up = ema_1h > ema_1h_prev
            else:
                ema_1h_trend_up = False
        except:
            ema_1h_trend_up = False
            
        return {**ind_15m, "ema_1h_trend_up": ema_1h_trend_up}

    def _compute_indicators(self, df: pd.DataFrame):
        # R4-6 FIX: Capture symbol BEFORE copy/tail — .tail() may not preserve .attrs
        symbol = df.attrs.get("symbol", "")
        
        # FIX M1: Increased tail from 100 to 210 to support EMA200 computation in check_ema_fan.
        # EMA200 requires 200+ data points to be statistically valid.
        # 100-candle trim was producing distorted/NaN EMA200 values.
        df = df.copy().tail(210)
        
        # Hardness Gate: Prevent library crashes (e.g. TA logic) on low data
        if len(df) < 20:
            return None
            
        price = df['close'].iloc[-1]
        
        vwap_series = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap_series(df)
        vwap = vwap_series.iloc[-1] if len(vwap_series) > 0 else df['close'].iloc[-1]
        distance_vwap = ((price - vwap) / vwap) * 100
        
        ema20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
        ema20 = ema20_series.iloc[-1]
        ema50 = EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]
        # FIX H1: Use raw single-candle diff for real-time slope (was rolling(3).mean() = 2-candle lag)
        ema_slope = ema20_series.diff().iloc[-1]
        
        avg_vol = df['volume'].rolling(20).mean()
        current_vol = df['volume'].iloc[-1]
        high, low = df['high'], df['low']
        
        # Clean RVOL logic: Benchmark against time-of-day if available, fallback to trailing avg
        # FIX #6: Use data timestamp instead of wall clock for RVOL benchmark
        # OLD: datetime.now() — late-batch stocks got stale benchmarks, breaks backtesting
        # NEW: use the actual candle's timestamp from the DataFrame index
        if isinstance(df.index, pd.DatetimeIndex) and len(df.index) > 0:
            time_bucket = df.index[-1].strftime("%H:%M")
        else:
            time_bucket = datetime.now().strftime("%H:%M")
        benchmark = liquidity_service.get_benchmark_vol(symbol, time_bucket)
        
        if benchmark > 0:
            rvol = current_vol / benchmark
        else:
            # FIX #6: Dynamic RVOL Divisor (Timeframe-Aware) [V16.1 Hardened]
            # OLD: Assumed fixed 25 candles (15m). 
            # NEW: Infer interval and calculate session density.
            if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 2:
                inferred_mins = (df.index[-1] - df.index[-2]).total_seconds() / 60
                if 1 <= inferred_mins <= 60:
                    candles_per_session = max(1, int(375 / inferred_mins))
                else:
                    candles_per_session = 25
            else:
                candles_per_session = 25
            
            liq_ctx = liquidity_service.get_liquidity(symbol)
            adv20 = liq_ctx.get("adv20", 0)
            
            if adv20 > 0:
                avg = adv20 / candles_per_session
            else:
                avg = avg_vol.iloc[-2] if len(avg_vol) > 1 else avg_vol.iloc[-1]
            
            rvol = current_vol / avg if avg > 0 else 0
        
        # FIX H3: Strengthen structure_ok with proper HH/HL check
        # OLD: price > recent_lows.min() was almost always True, letting downtrending stocks pass EARLY mode
        # NEW: require the last candle low to be HIGHER THAN the low 3 candles ago (Higher Low confirmation)
        if len(df) >= 5:
            recent_highs = df['high'].tail(5)
            recent_lows = df['low'].tail(5)
            # Higher Low: current low > low from 3 bars ago (upward structure)
            hl_confirmed = df['low'].iloc[-1] > df['low'].iloc[-4]
            # Not making Lower Highs: last high >= second-to-last high
            no_lower_high = df['high'].iloc[-1] >= df['high'].iloc[-2] * 0.998  # 0.2% tolerance
            structure_ok = hl_confirmed and no_lower_high and price > recent_lows.min()
        else:
            structure_ok = price >= low.iloc[-2] if len(low) >= 2 else True
        
        # V16 AUDIT FIX 1: Compute ATR BEFORE pullback check so we can use ATR-normalized proximity
        atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_indicator.average_true_range().iloc[-1]
        
        # P7 FIX: Broader pullback definition — catches 9EMA and VWAP bounces, not just EMA20
        # V16 AUDIT FIX 1: Replace static percentage tolerances with ATR-normalized proximity.
        # OLD: c_low <= c_ema20 * 1.015 (1.5% static) — flagged virtually every trending stock as "pullback"
        # NEW: c_low <= c_ema20 + (atr * 0.3) — self-adjusts to volatility. Tight for calm stocks, wider for volatile.
        ema9_series = EMAIndicator(close=df['close'], window=9).ema_indicator()
        ema9 = ema9_series.iloc[-1]
        
        touched_support = False
        if len(df) >= 3:
            for i in range(-3, 0):
                c_low = df['low'].iloc[i]
                c_ema20 = ema20_series.iloc[i]
                c_ema9 = ema9_series.iloc[i]
                c_vwap = vwap_series.iloc[i] if len(vwap_series) >= 3 else vwap
                # ATR-normalized: EMA20 within 0.3 ATR, EMA9 within 0.2 ATR, VWAP within 0.15 ATR
                if c_low <= c_ema20 + (atr * 0.3) or c_low <= c_ema9 + (atr * 0.2) or c_low <= c_vwap + (atr * 0.15):
                    touched_support = True
                    break
        else:
            touched_support = low.iloc[-1] <= ema20 + (atr * 0.3)
            
        trend_resuming = df['close'].iloc[-1] > df['close'].iloc[-2]
        is_pullback = touched_support and trend_resuming and price > ema20
        
        distance_ema = ((price - ema20) / ema20) * 100
        # Dynamic Institutional Exhaustion: Scaled by ATR (3x ATR Band)
        exhaustion_limit = (atr * 3 / price) * 100 if price > 0 else 5.0
        # FIX #3: Changed OR to AND — gap-up stocks were immediately killed by VWAP distance alone
        # A stock that opens 4% above VWAP (gap-and-go) shouldn't be flagged exhausted
        # unless it's ALSO stretched from EMA20. Both conditions must be true.
        # V14.6 FIX: Bi-directional exhaustion (absolute distance)
        is_exhausted = abs(distance_vwap) > 3.5 and abs(distance_ema) > exhaustion_limit
        
        # FIX C2: Compute pa_score here so Smart Gate can use it
        # (Same logic as analyze_stock: close in top 20% of candle = aggressive buying)
        last_candle = df.iloc[-1]
        c_range = last_candle['high'] - last_candle['low']
        close_relative = (price - last_candle['low']) / c_range if c_range > 0 else 0.5
        pa_score = 100 if close_relative > 0.8 and rvol > 1.2 else (80 if close_relative > 0.8 else (50 if close_relative > 0.5 else 0))

        if pd.isna(price) or pd.isna(ema20) or pd.isna(vwap) or pd.isna(rvol):
            return None
            
        return {
            "symbol": symbol, 
            "price": price, 
            "ema20": ema20, 
            "ema50": ema50,
            "ema_slope": ema_slope, 
            "vwap": vwap,
            "vwap_val": vwap,  # FIX C1: Add alias so Smart Gate's vwap_val check works correctly
            "distance_vwap": distance_vwap, 
            "distance_ema": distance_ema,
            "rvol": rvol, 
            "structure_ok": structure_ok, 
            "is_pullback": is_pullback, 
            "is_exhausted": is_exhausted,
            "atr": atr,
            "pa_score": pa_score  # FIX C2: pa_score now populated for Smart Gate
        }

    def _run_layer1(self, indicators):
        price, ema20, ema_slope = indicators["price"], indicators["ema20"], indicators["ema_slope"]
        distance_vwap, rvol = indicators["distance_vwap"], indicators["rvol"]
        score, reasons = 0, []
        
        # DNA Recalibration: 10 points per check (Total 40)
        if price > ema20: 
            score += 10; reasons.append({"text": "Price above EMA20", "impact": 10})
        if ema_slope > 0: 
            score += 10; reasons.append({"text": "EMA20 trending up", "impact": 10})
        
        # FIX M2: Corrected VWAP bias tracking (No absolute hacks that turn dropping stocks positive)
        if 0 <= distance_vwap < 1.5: 
            score += 10; reasons.append({"text": "Near VWAP (healthy trend)", "impact": 10})
        elif distance_vwap >= 1.5: 
            score += 5; reasons.append({"text": "Extended from VWAP", "impact": 5})
        elif -1.5 < distance_vwap < 0:
            score -= 2; reasons.append({"text": "Slightly below VWAP (chop risk)", "impact": -2})
        elif distance_vwap <= -1.5:
            score -= 5; reasons.append({"text": "Below VWAP (bearish bias)", "impact": -5})
        
        # P3 FIX: Added RVOL 0.8-1.2 tier — average volume is NORMAL, not bearish
        if rvol > 2: 
            score += 10; reasons.append({"text": "High RVOL (institutional volume)", "impact": 10})
        elif rvol > 1.2: 
            score += 6; reasons.append({"text": "Above avg volume", "impact": 6})
        elif rvol > 0.8:
            score += 3; reasons.append({"text": "Normal volume", "impact": 3})
        
        # FIX #1: Floor at 0 — L1 can go negative (-5 from below-VWAP penalty)
        # which silently penalised final_score beyond what L3 already deducts
        return max(0, min(40, score)), {"score": score, "reasons": reasons}

    # R4-4 FIX: Removed unused df_15m, df_1h params — L2 only reads from indicators dict.
    # FUTURE: Adding candle pattern analysis (engulfing, hammer at VWAP) from df_15m
    # would significantly improve L2 entry quality detection.
    def _run_layer2(self, indicators, df_15m=None):
        price, ema20, distance_vwap = indicators["price"], indicators["ema20"], indicators["distance_vwap"]
        rvol, structure_ok, is_pullback = indicators["rvol"], indicators["structure_ok"], indicators["is_pullback"]
        # FIX R11: Dead Gate revived. Use correctly populated dictionary key 'is_exhausted'.
        is_exhausted = indicators.get("is_exhausted", False)
        ema_1h_trend_up = indicators["ema_1h_trend_up"]
        score, reasons, alpha_mode = 0, [], "NONE"
        dynamic_zones = {}
        
        # 1. Exhaustion Phase (EXT) Gate
        if is_exhausted:
            alpha_mode = "EXHAUSTED"
            reasons.append({"text": "Price over-extended (EXT Phase) - High Risk of Mean Reversion", "impact": 0})
            
            # P5 FIX: Check bearish divergence even for exhausted stocks
            if df_15m is not None:
                try:
                    rsi_div = ta_intraday.IntradayTechnicalAnalysis.detect_rsi_divergence(df_15m)
                    if rsi_div.get("type") == "Bearish":
                        reasons.append({"text": "EXHAUSTED + Bearish Divergence (AVOID)", "impact": 0})
                except Exception:
                    pass
                    
            return 0, {"score": 0, "mode": alpha_mode, "reasons": reasons, "dynamic_zones": dynamic_zones}
            
        # P13 FIX: Compute confluence signals here, AFTER exhaustion check
        # This prevents wasting CPU computing signals for exhausted stocks
        if df_15m is not None:
            try:
                indicators["rsi_divergence"] = ta_intraday.IntradayTechnicalAnalysis.detect_rsi_divergence(df_15m)
                indicators["squeeze"] = ta_intraday.IntradayTechnicalAnalysis.detect_squeeze(df_15m)
                indicators["cvd"] = ta_intraday.IntradayTechnicalAnalysis.calculate_cvd_proxy(df_15m)
                indicators["ema_fan"] = ta_intraday.IntradayTechnicalAnalysis.check_ema_fan(df_15m)
                indicators["poc_bounce"] = ta_intraday.IntradayTechnicalAnalysis.detect_poc_bounce(df_15m)
                indicators["accumulation"] = ta_intraday.IntradayTechnicalAnalysis.detect_smart_money_accumulation(df_15m)
                # [V20 VANGUARD] Fair Value Gap Check
                indicators["fvg"] = ta_intraday.IntradayTechnicalAnalysis.detect_bullish_fvg(df_15m)
            except Exception:
                pass

        distance_vwap_abs = abs(distance_vwap)
        is_near_vwap, is_trending = distance_vwap_abs < 1.2, price > ema20
        
        # 2. Alpha Mode Sequence Gate (Total Target: 60)
        # Sequence Priority: 1. Breakout -> 2. Pullback -> 3. Momentum -> 4. Early Base
        
        # 2A. Breakout Phase (Highest Conviction, must check first so it's not hijacked by 'EARLY')
        if indicators.get("accumulation", {}).get("is_breakout", False):
            bk_ctx = indicators.get("accumulation", {})
            bk_score = bk_ctx.get("breakout_score", 0)
            bk_pts = 45 if bk_score >= 60 else 35
            alpha_mode = "BREAKOUT"; score += bk_pts; reasons.append({"text": f"BREAKOUT: {bk_ctx.get('breakout_intensity', 'Valid')} from tight zone", "impact": bk_pts})

        # 2B. Pullback Phase
        elif is_pullback:
            pb_score = 35
            pb_reason = "PULLBACK: EMA retracement + recovery"
            if df_15m is not None:
                try:
                    # V16.1 Context Injection: Pass Smart Gate and Volatility characteristics
                    liq_ctx = liquidity_service.get_liquidity(indicators.get("symbol", ""))  # V18 FIX #5
                    vol_mult = 1.25 if liq_ctx.get("level") in ["High", "Moderate"] else 1.0
                    
                    pb_context = {
                        "smart_gate": indicators.get("smart_gate_bypass", False),
                        "vol_mult": vol_mult
                    }
                    
                    pb_engine = ta_intraday.IntradayTechnicalAnalysis.detect_pullback_entry_v45(
                        df_15m, 
                        indicators.get("vwap_val", price),
                        context=pb_context
                    )
                    
                    dynamic_zones["stop_loss"] = pb_engine.get("stop_loss")
                    dynamic_zones["target"] = pb_engine.get("target_2")
                    adv_score = pb_engine.get("entry_score", 0)
                    if adv_score >= 70:
                        pb_score = 45
                        pb_reason = f"PULLBACK (V4.5 Verified) - Quality: {pb_engine.get('entry_quality', 'B')}"
                        if pb_engine.get("signals", {}).get("liquidity_sweep"):
                            score += 10; reasons.append({"text": "Confluence: Stop-Hunt Trap (Liquidity Sweep)", "impact": 10})
                except Exception:
                    pass
            
            # [V20 VANGUARD] Fair Value Gap (+20 pts)
            fvg = indicators.get("fvg", {})
            if fvg.get("is_tapping"):
                pa_score = indicators.get("pa_score", 0)
                if pa_score > 60: # Validates it's rejecting the FVG upwards
                    pb_score += 20
                    pb_reason += " + FVG Defense (SMART MONEY)"
            
            alpha_mode = "PULLBACK"; score += min(60, pb_score); reasons.append({"text": pb_reason, "impact": min(60, pb_score)})
            
        # 2C. Momentum Phase
        elif is_trending and distance_vwap > 1.2 and rvol > 1.5:
            alpha_mode = "MOMENTUM"; score += 40; reasons.append({"text": "MOMENTUM: Strong trend + volume", "impact": 40})
            
        # 2D. Early Phase Base (Catch-all for standard healthy setups that aren't explosive yet)
        elif is_near_vwap and is_trending and structure_ok:
            alpha_mode = "EARLY"; score += 45; reasons.append({"text": "EARLY: Near VWAP + Trend + Structure", "impact": 45})
        
        # [V19 APEX-C] OPENING DRIVE DETECTION (9:15-9:45)
        # The most profitable intraday window — gap-and-go, ORB breakouts, institutional opening orders
        if alpha_mode == "NONE" and df_15m is not None and isinstance(df_15m.index, pd.DatetimeIndex):
            try:
                od_h, od_m = df_15m.index[-1].hour, df_15m.index[-1].minute
                is_opening_window = (od_h == 9 and 15 <= od_m <= 45)
                if is_opening_window:
                    orb = indicators.get("orb", {})
                    gap = indicators.get("gap", {})
                    # Gap-and-Go: gap > 0.5% with strong volume
                    is_gap_go = gap.get("gap_percent", 0) > 0.5 and rvol > 2.0
                    # ORB Breakout: above opening range high
                    is_orb = orb.get("breakout_type") == "bullish"
                    if is_gap_go or is_orb:
                        alpha_mode = "OPENING_DRIVE"
                        score += 42; reasons.append({"text": f"OPENING DRIVE: {'Gap-and-Go' if is_gap_go else 'ORB Breakout'}", "impact": 42})
            except Exception:
                pass
            
        if rvol > 2.5: score += 10; reasons.append({"text": "Booster: High RVOL", "impact": 10})
        if ema_1h_trend_up: score += 5; reasons.append({"text": "Booster: 1H Trend Up", "impact": 5})
        
        # R5-3 FIX: Signal Confluence Boosters
        # These only fire when a valid alpha mode has been detected (EARLY/PULLBACK/MOMENTUM).
        # They CONFIRM the setup quality — they don't create phantom signals.
        # Without confluence, PULLBACK max=50 and MOMENTUM max=45, never reaching 60.
        if alpha_mode != "NONE":
            # 1. Bullish RSI Divergence: Price Lower Low but RSI Higher Low → reversal confirmation
            rsi_div = indicators.get("rsi_divergence", {})
            if rsi_div.get("type") == "Bullish":
                bonus = 8 if rsi_div.get("severity") == "High" else 5
                score += bonus; reasons.append({"text": f"Confluence: Bullish RSI Divergence ({rsi_div.get('severity', 'Moderate')})", "impact": bonus})
            
            # 2. Squeeze Breakout: Bollinger squeeze releasing → explosive energy
            squeeze = indicators.get("squeeze", {})
            if squeeze.get("is_breakout") and squeeze.get("is_squeeze"):
                score += 7; reasons.append({"text": "Confluence: Squeeze Breakout (energy release)", "impact": 7})
            elif squeeze.get("is_squeeze"):
                score += 3; reasons.append({"text": "Confluence: Squeeze Building (coiling energy)", "impact": 3})
            
            # 3. CVD Accumulation: Net buying volume confirms institutional flow direction
            cvd = indicators.get("cvd", {})
            if cvd.get("score", 50) >= 75:
                score += 5; reasons.append({"text": f"Confluence: Institutional Accumulation (CVD {cvd.get('cvd_ratio', 0):+.0%})", "impact": 5})
            
            # 4. EMA Fan Alignment: 9 > 20 > 50 > 200 = textbook bullish structure
            ema_fan = indicators.get("ema_fan", {})
            if ema_fan.get("status") == "Bullish Fan":
                score += 5; reasons.append({"text": "Confluence: Bullish EMA Fan (9>20>50>200)", "impact": 5})
                
            # 5. POC Bounce: Volume profile defense line
            poc_bounce = indicators.get("poc_bounce", {})
            if poc_bounce.get("is_bounce"):
                score += 10; reasons.append({"text": "Confluence: V-POC Bounce (Volume Node Defense)", "impact": 10})
            
            # [V18 FIX #18] Candle Pattern Recognition at Key Levels
            if df_15m is not None and len(df_15m) >= 3:
                last = df_15m.iloc[-1]
                prev = df_15m.iloc[-2]
                c_range = float(last['high']) - float(last['low'])
                body = abs(float(last['close']) - float(last['open']))
                lower_wick = min(float(last['close']), float(last['open'])) - float(last['low'])
                
                vwap_val = indicators.get("vwap_val", 0)
                atr = indicators.get("atr", max(c_range, 1e-6))
                ema20 = indicators.get("ema20", 0)
                
                # Bullish Hammer at VWAP/EMA20 (lower wick > 2x body, near support)
                is_hammer = (lower_wick > body * 2) and (float(last['close']) > float(last['open'])) and c_range > 0
                near_support = (abs(float(last['low']) - vwap_val) < atr * 0.3) or (abs(float(last['low']) - ema20) < atr * 0.3)
                
                if is_hammer and near_support:
                    score += 8; reasons.append({"text": "Confluence: Bullish Hammer at Support", "impact": 8})
                
                # Bullish Engulfing
                is_engulfing = (
                    float(prev['close']) < float(prev['open']) and   # prev bearish
                    float(last['close']) > float(last['open']) and   # curr bullish
                    float(last['close']) > float(prev['open']) and   # body engulfs
                    float(last['open']) < float(prev['close'])
                )
                if is_engulfing and indicators.get("rvol", 0) > 1.2:
                    score += 7; reasons.append({"text": "Confluence: Bullish Engulfing (reversal)", "impact": 7})
                
        # P17: Smart Gate Reversal Booster
        # If the stock bypassed the DNA block via conviction signals, inject 15 points
        # to counteract the L1 penalties safely.
        if indicators.get("smart_gate_bypass", False):
            score += 15; reasons.append({"text": "Confluence: Conviction Reversal (Smart Gate Bypass)", "impact": 15})
        
        # FIX C4 & V14.6: Hard Alpha Lock - Guard against phantom conviction from booster-only scores
        if alpha_mode == "NONE":
            # Boosters alone are not enough — no directional edge identified
            return 0, {"score": 0, "mode": "NONE", "reasons": [{"text": "No Alpha Mode: No directional edge (EARLY/PULLBACK/MOMENTUM) detected", "impact": 0}], "dynamic_zones": {}}

        # Adjust individual impacts if capped at 60
        if score > 60:
            diff = score - 60
            if reasons: reasons[0]["impact"] -= diff # Simple adjustment

        return min(60, score), {"score": score, "mode": alpha_mode, "reasons": reasons, "dynamic_zones": dynamic_zones}

    def _run_layer3(self, indicators, df_15m, market_ctx, l2_data=None, liq=None):
        price, ema20, rvol, atr = indicators["price"], indicators["ema20"], indicators["rvol"], indicators["atr"]
        penalty, reasons = 0, []
        alpha_mode = l2_data.get("mode", l2_data.get("alpha_mode", "NONE")) if l2_data else "NONE"
        
        # V14.1 FIX: Smart L3 EMA Penalty (Synced with Step 1 Smart Gate)
        # We use the smart_gate_bypass flag to acknowledge high-conviction recoveries.
        is_below_ema = price < ema20
        has_conviction = indicators.get("smart_gate_bypass", False)
        if is_below_ema and not has_conviction:
            penalty += 25; reasons.append({"text": "Penalty: Below EMA20 (no conviction reclaim)", "impact": -25})
        elif is_below_ema and has_conviction:
            penalty += 10; reasons.append({"text": "Caution: Below EMA20 (smart gate recovery in progress)", "impact": -10})
        
        distance_ema = abs((price - ema20) / ema20) * 100
        
        # P2 FIX: Tightened chop threshold to 0.8 to avoid double-penalizing stocks with RVOL 1.0-1.2
        # OLD: rvol < 1.2 fired BOTH chop (-10) AND low RVOL (-15) = -25 total for normal volume
        if distance_ema < 0.5 and alpha_mode != "PULLBACK" and rvol < 0.8: 
            penalty += 10; reasons.append({"text": "Penalty: Too close to EMA on dead volume (chop risk)", "impact": -10})
        
        if rvol < 0.8: 
            penalty += 15; reasons.append({"text": "Penalty: Low RVOL (no institutional volume)", "impact": -15})
        
        # [V12.9] Liquidity Constraint
        if not liq:
            liq = liquidity_service.get_liquidity(indicators.get("symbol", ""))
            
        adv20 = liq.get("adv20", 0)
        daily_turnover = adv20 * price
        # FIX C3: Align threshold with Fix #4 turnover bands
        # OLD: threshold was ₹5Cr (50M) — inconsistent with new 'Very Low' = <₹1Cr
        # NEW: penalty at < ₹2Cr, which is the institutional minimum for safe intraday participation
        if daily_turnover < 20_000_000 and adv20 > 0:  # ₹2 Crore minimum
            penalty += 20; reasons.append({"text": "Penalty: Low Daily Turnover (< ₹2 Cr)", "impact": -20})
        # R4-9 FIX: Unknown liquidity (adv20 == 0) should get FULL penalty, not a pass
        elif adv20 == 0:
            penalty += 20; reasons.append({"text": "Penalty: Unknown Liquidity (no ADV20 data)", "impact": -20})
        
        last_candle = df_15m.iloc[-1]; high, low, close = last_candle['high'], last_candle['low'], last_candle['close']
        candle_range = high - low
        # P8 FIX: Only penalize upper wick on BEARISH candles (close < open)
        # OLD: fired on ANY candle with close in bottom half — including bullish hammers
        if candle_range > 0 and (high - close) / candle_range > 0.5 and close < last_candle['open']:
            penalty += 15; reasons.append({"text": "Penalty: Bearish upper wick (selling pressure)", "impact": -15})
            
        # FIX H2: Use actual trade risk (entry - stop_loss) not EMA distance
        # OLD: risk = abs(price - ema20) — this is EMA distance, not the trade's stop distance
        # This made RR ratio meaningless (ATR reward / EMA distance risk = wrong units)
        # NEW: use ATR-based stop distance (same as the engine's stop_loss calc in Fix #3)
        actual_sl_distance = max(atr * 1.5, price * 0.005)  # Mirror of Fix #3 stop_loss formula
        risk = actual_sl_distance if actual_sl_distance > 0 else (atr * 0.5)
        # V14.6 FIX: Decouple baseline structural reward from volume velocity to prevent double penalization.
        reward_mult = 3.0 if rvol > 2.5 else 2.0
        reward = atr * reward_mult
        rr_ratio = reward / risk if risk > 0 else 0
        if rr_ratio < 1.2: 
            penalty += 15; reasons.append({"text": f"Penalty: Poor Risk/Reward ({rr_ratio:.1f})", "impact": -15})
        
        # V15 Pioneer Fix: Time Decay Matrix
        try:
            if df_15m is not None and not df_15m.empty:
                current_time = df_15m.index[-1]
                if hasattr(current_time, 'hour'):
                    h, m = current_time.hour, current_time.minute
                    
                    # V16.1: LOTTO PASS [Hardened]
                    # If the score is exceptional (A+ quality) or volume is parabolic, we reduce time-decay 
                    # to allow high-conviction 'Hero' trades during typical dead zones.
                    is_lotto = (l2_data.get("score", 0) >= 100) or (rvol > 4.0)
                    t_mult = 0.5 if is_lotto else 1.0
                    
                    # Lunch Chop Filter (11:30 to 13:30)
                    if (h == 11 and m >= 30) or h == 12 or (h == 13 and m <= 30):
                        p_val = int(20 * t_mult)
                        reasons.append({"text": f"Penalty: Lunch Chop Zone (Time Decay {'[LOTTO PASS]' if is_lotto else ''})", "impact": -p_val})
                        penalty += p_val
                    # [V19 APEX-D] POWER HOUR (14:00 - 14:45): Institutional accumulation window
                    elif h == 14 and m < 45:
                        if rvol > 1.5:
                            # Power Hour with volume = institutional accumulation — no penalty
                            reasons.append({"text": "Boost: Power Hour Momentum (14:00-14:45)", "impact": 0})
                        else:
                            p_val = 5  # Mild caution for low-volume Power Hour
                            penalty += p_val
                            reasons.append({"text": "Caution: Power Hour (low volume)", "impact": -p_val})
                    # EOD Liquidation Risk Filter (After 14:45)
                    elif (h == 14 and m >= 45) or h >= 15:
                        p_val = int(30 * t_mult)
                        reasons.append({"text": f"Penalty: End Of Day Liquidation Risk {'[LOTTO PASS]' if is_lotto else ''})", "impact": -p_val})
                        penalty += p_val
        except Exception:
            pass

        # Global Market Regime Integration
        if market_ctx:
            regime = market_ctx.get("market_regime", "Mixed")
            is_sideways = market_ctx.get("is_sideways", False)
            
            if regime == "Strong Bearish":
                penalty += 20; reasons.append({"text": "Penalty: Extreme Market Weakness (Nifty Bearish)", "impact": -20})
            elif is_sideways and rvol < 2.0:
                penalty += 10; reasons.append({"text": "Penalty: Sideways Market (Low Momentum Filter)", "impact": -10})
        
        # Safe Momentum Check (Requires at least 4 candles)
        if len(df_15m) >= 4:
            recent_highs, prev_high = df_15m['high'].iloc[-3:], df_15m['high'].iloc[-4]
            if recent_highs.max() <= prev_high: 
                penalty += 5; reasons.append({"text": "Penalty: No momentum (stale move)", "impact": -5})

        # V16 AUDIT FIX 4: Daily (1D) Macro Trend Penalty
        # If stock is below its Daily 20-EMA, trend-following setups have dramatically lower probability.
        # NOT a hard block — exceptional setups can still overcome the -25 penalty.
        is_1d_bullish = indicators.get("is_1d_bullish", True)
        if not is_1d_bullish and alpha_mode in ["BREAKOUT", "PULLBACK", "EARLY", "MOMENTUM"]:
            penalty += 25; reasons.append({"text": "Penalty: Below Daily 20-EMA (Counter-Trend Risk)", "impact": -25})
        
        # P1/P10 FIX: Penalize Bearish RSI Divergence (reversal risk)
        # OLD: Only rewarded bullish divergence in L2, ignored bearish entirely
        rsi_div = indicators.get("rsi_divergence", {})
        if rsi_div.get("type") == "Bearish":
            pen = 15 if rsi_div.get("severity") == "High" else 10
            penalty += pen; reasons.append({"text": f"Penalty: Bearish RSI Divergence (reversal risk)", "impact": -pen})
        
        # P11 FIX: Penalize CVD Distribution (smart money selling)
        cvd = indicators.get("cvd", {})
        if cvd.get("score", 50) <= 25:
            penalty += 10; reasons.append({"text": "Penalty: Smart Money Distribution (CVD net selling)", "impact": -10})
        
        # P12 FIX: Penalize Bearish EMA Fan (textbook downtrend structure)
        ema_fan = indicators.get("ema_fan", {})
        if ema_fan.get("status") == "Bearish Fan":
            penalty += 15; reasons.append({"text": "Penalty: Bearish EMA Fan (9<20<50<200)", "impact": -15})
        
        # P9 FIX: Time-of-day awareness — opening noise filtering
        # V16 AUDIT FIX 2: Removed duplicate lunch penalty (was stacking -25 with V15 Time Decay at L637)
        if isinstance(df_15m.index, pd.DatetimeIndex) and len(df_15m.index) > 0:
            hour = df_15m.index[-1].hour
            minute = df_15m.index[-1].minute
            current_mins = hour * 60 + minute
            if current_mins < 570:  # Before 9:30 AM
                penalty += 10; reasons.append({"text": "Penalty: Opening volatility (pre-9:30 noise)", "impact": -10})
        
        return penalty, {"penalty": penalty, "reasons": reasons}

    def _get_signal(self, score):
        if score >= 85: return "BUY_STRONG"
        elif score >= 60: return "BUY"
        elif score >= 40: return "NEUTRAL"
        else: return "IGNORE"

    async def run_scan(self, job_id: str, logger=None):
        """[V10 SPEED] Pulse-Fire Main Loop with [V11 TIMEOUT PROTECTION]."""
        from app.services.market_discovery import market_discovery
        symbols = await market_discovery.get_full_market_list()
        if not symbols: return {"status": "error"}

        total = len(symbols)
        print(f"[SCAN] Pulse Scan: {total} symbols")
        
        # [V13.1] Initialize services before scan
        await liquidity_service.initialize()
        await kite_service.initialize()
        
        # [V13.5] Bulk Bootstrap liquidity for all symbols in the current scan
        all_symstr = [s["symbol"] if isinstance(s, dict) else s for s in symbols]
        asyncio.create_task(liquidity_service.bulk_bootstrap(all_symstr))
        
        # [V17 Vanguard] Bootstrap Synchronization Guard
        # Give the background task a few seconds to kick off and fetch the first few batches
        # This prevents the initial batch of a scan from falling back to ADV25.
        await asyncio.sleep(2)
        
        self.job_states[job_id] = {"results": [], "failed_symbols": [], "progress": 0, "is_running": True, "pause_requested": False, "main_task": asyncio.current_task()}
        index_ctx = await self._get_index_context()
        
        # [V18 FIX #6] Pre-compute sector heat ONCE globally (not per-batch)
        try:
            sector_heat = await market_service.get_sector_performances()
            # Convert from percentage to decimal for compatibility with gating thresholds
            sector_heat = {k: v / 100.0 for k, v in sector_heat.items()}
        except Exception as e:
            print(f"[SECTOR] Failed to fetch global sector heat: {e}")
            sector_heat = {}
        
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        # R4-8 FIX: Pre-build O(1) index lookup instead of O(n) symbols.index() per stock
        symbol_index_map = {(s["symbol"] if isinstance(s, dict) else s): i for i, s in enumerate(symbols)}

        try:
            # Process in Streaming Batches of 100
            chunk_size = 100
            for i in range(0, total, chunk_size):
                if job_id in self.job_states and not self.job_states[job_id].get("is_running", True):
                    if logger: logger.warning(f"[STOP] [INTRA] Stop Signal Received. Terminating job {job_id} at {i}/{total}.")
                    break

                # [V12.1 PAUSE CHECK] ⏸️
                while job_id in self.job_states and self.job_states[job_id].get("pause_requested"):
                    if not self.job_states[job_id].get("is_running", True): break
                    await asyncio.sleep(1)

                chunk = symbols[i:i + chunk_size]
                chunk_syms = [s["symbol"] if isinstance(s, dict) else s for s in chunk]
                
                print(f"[BATCH] Pulse Batch: {i}/{total} ({len(chunk_syms)} symbols)")
                
                # 1. Fetch data for this specific batch (with 120s HARD TIMEOUT)
                try:
                    res_15m, res_1h, res_1d, res_prices = await asyncio.wait_for(
                        asyncio.gather(
                            market_service.get_batch_ohlc(chunk_syms, interval="15m", period="7d"),
                            market_service.get_batch_ohlc(chunk_syms, interval="60m", period="15d"),
                            market_service.get_batch_ohlc(chunk_syms, interval="1d", period="3mo"),  # V16 FIX 4: Daily trend data
                            market_service.get_batch_prices(chunk_syms)
                        ),
                        timeout=120.0
                    )
                except asyncio.TimeoutError:
                    print(f"[TIMEOUT] Batch {i} hung. Force-skipping to maintain engine flow.")
                    self.job_states[job_id]["progress"] += len(chunk)
                    continue

                batch_pulse = {}
                for s in chunk_syms:
                    batch_pulse[s] = {"15m": res_15m.get(s), "1h": res_1h.get(s), "1d": res_1d.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}

                # [V18 FIX #6] Sector heat now pre-computed globally before scan loop
                # sector_heat = await self._calculate_sector_heat(batch_pulse)  # REMOVED: was per-batch

                # 2. Analyze the batch immediately
                async def sem_task(s_obj):
                    sym = s_obj["symbol"] if isinstance(s_obj, dict) else s_obj
                    async with self.semaphore:
                        try:
                            # [PER-STOCK LOGGING REQUESTED]
                            res = await asyncio.wait_for(
                                self.analyze_stock(sym, job_id, index_ctx, batch_pulse, sector_heat),
                                timeout=10.0
                            )
                            
                            if res and "skip_reason" not in res: 
                                # [V14.6 SEQUENCE PERSISTENCE] Add index to preserve discovery order
                                res["analysis_index"] = symbol_index_map.get(sym, 0)
                                self.job_states[job_id]["results"].append(res)
                                if logger:
                                    # [V12.7 HIGH-TRANSPARENCY LOGGER]
                                    l1 = res.get("groups", {}).get("DNA (40%)", {}).get("score", 0)
                                    l2 = res.get("groups", {}).get("Alpha Edge (60%)", {}).get("score", 0)
                                    l3 = res.get("groups", {}).get("Safeguards (L3)", {}).get("score", 0)
                                    
                                    reasons = res.get("reasons", [])
                                    catalysts = [r["text"] for r in reasons if r.get("impact", 0) > 0 and r.get("layer") in [1, 2]]
                                    penalties = [r["text"] for r in reasons if r.get("impact", 0) < 0 and r.get("layer") == 3]
                                    
                                    liq_info = res.get("liquidity", {})
                                    cap_str = f"{liq_info.get('max_stealth_buy_qty', 0):,}"
                                    
                                    if res['signal'] == 'IGNORE':
                                        logger.info(f"SKIP {sym}: {res.get('skip_reason', 'Threshold')}")
                                    else:
                                        # [V13] INSTITUTIONAL LOG TRACE
                                        flags = [k for k, v in res.get("flags", {}).items() if v]
                                        flag_str = "|".join(flags) if flags else "None"
                                        msg = f"{sym:10} | Score:{res['score']:>4} | RS:{res.get('rs_alpha', 0):>6.4f} | Regime:{res['regime']:10} | Mode:{res['mode']:10} | Flags:[{flag_str}]"
                                        logger.info(msg)
                                        # Institutional detail logging
                                        if catalysts or penalties:
                                            print(f"   ├ 🚀 Catalysts: {', '.join(catalysts[:4])}") if catalysts else None
                                            print(f"   ├ 🛡️ Penalties: {', '.join(penalties[:4])}") if penalties else None
                            else:
                                if logger: logger.warning(f"[SKIP] {sym}: {res.get('skip_reason', 'Unknown')}")
                        except Exception as e:
                            import traceback
                            traceback.print_exc()
                            if logger: logger.error(f"[ERROR] {sym}: Analysis ERROR: {str(e)}")
                            pass
                        finally:
                            self.job_states[job_id]["progress"] += 1

                await asyncio.gather(*[sem_task(s) for s in chunk])

                # 6. Safety Delay (V16.1 Evasion Hardening)
                # Spacing out batches to prevent 'robotic' request signatures
                if i + chunk_size < total:
                    delay = random.uniform(1.5, 3.0)
                    await asyncio.sleep(delay)

                
        finally:
            self.job_states[job_id]["is_running"] = False
            await sync_task

        # --- L4: ALLOCATION LAYER ---
        raw_results = self.job_states[job_id]["results"]
        
        # [V19 APEX-B] ADAPTIVE SCORE FLOOR BY REGIME
        # STRONG_TREND: trend carries trades → loosen gate
        # CHOP: only highest conviction → tighten gate
        regime_strength = self.system_state.get("regime_strength", "NORMAL")
        if regime_strength == "STRONG_TREND":
            dynamic_floor = 55   # Trend carries — capture momentum runners
        elif regime_strength == "CHOP":
            dynamic_floor = 80   # Only highest conviction survives
        else:
            dynamic_floor = self.CONFIG["score_floor"]  # Standard 65
        
        filtered = [r for r in raw_results if r.get("score", 0) >= dynamic_floor]
        
        # 2. Top-N Selection (15% or Max 50)
        top_n_target = min(self.CONFIG["top_n_cap"], max(5, int(len(filtered) * 0.15)))
        
        # 3. Final Sorting (Priority DESC, Footprint Tie-Break)
        # We use a small epsilon for priority tie-breaking
        results = sorted(
            filtered, 
            key=lambda x: (x.get("priority", 0), x.get("flags", {}).get("FOOTPRINT", 0)), 
            reverse=True
        )[:top_n_target]
        
        # 4. System State Synchronization
        self._sync_scans_and_risk(results)
        
        # 5. Cross-Scan Persistence Update
        for res in results:
            sym = res["symbol"]
            if sym not in self.persistence_cache: self.persistence_cache[sym] = []
            self.persistence_cache[sym].append({"score": res["score"], "time": datetime.utcnow()})
            # Keep only last 5 scans
            if len(self.persistence_cache[sym]) > 5: self.persistence_cache[sym].pop(0)

        return sanitize_data({
            "total": total, 
            "success": len(results), 
            "system_state": self.system_state,
            "data": results
        })

    async def stop_job(self, job_id: str):
        """[V12.1 RESTORED] Programmatic termination signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["is_running"] = False
            print(f"[STOP] Signal sent to stop job {job_id}")

    async def pause_job(self, job_id: str):
        """[V12.1] Pause terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"[PAUSE] Signal sent to pause job {job_id}")

    async def resume_job(self, job_id: str):
        """[V12.1] Resume terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"[RESUME] Signal sent to resume job {job_id}")

    async def _progress_loop(self, job_id: str, total: int):
        while job_id in self.job_states and self.job_states[job_id]["is_running"]:
            try:
                state = self.job_states[job_id]
                async with AsyncSessionLocal() as session:
                    job = await session.get(Job, job_id)
                    if job:
                        # [V12.1 EXTERNAL CANCEL CHECK] 🛑
                        if job.status in ["failed", "cancelled", "stopped"]:
                            state["is_running"] = False
                            # [V12.2] Explicitly cancel the main execution task
                            main_task = state.get("main_task")
                            if main_task and not main_task.done():
                                main_task.cancel()
                            break
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ⏸️
                        if job.status == "paused":
                            state["pause_requested"] = True
                        elif state.get("pause_requested") and job.status == "processing":
                            state["pause_requested"] = False

                        job.result = sanitize_data({
                            "progress": state["progress"], "total_steps": total,
                            # FIX H5: Align live progress sort with final output sort (score DESC, analysis_index ASC)
                            # OLD: sorted by score only — caused different ranking during scan vs final result
                            "data": sorted(
                                state["results"],
                                key=lambda x: (x.get("score", 0), -(x.get("analysis_index", 0))),
                                reverse=True
                            )[:500],
                            "status_msg": f"V11 Pulse Scan: {state['progress']}/{total}"
                        })
                        flag_modified(job, "result")
                        await session.commit()
            # R4-7 FIX: Log progress loop errors instead of silently swallowing them
            except Exception as e:
                print(f"[PROGRESS_LOOP] DB write error for job {job_id}: {e}")
            await asyncio.sleep(2.5)

intraday_engine = IntradayEngine()
