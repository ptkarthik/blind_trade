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
    @property
    def semaphore(self):
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.CONFIG.get("concurrency", 25))
        return self._semaphore

    def __init__(self):
        # [V13] CENTRALIZED INSTITUTIONAL CONFIG
        self.CONFIG = {
            "version": "V13-PIONEER",
            "concurrency": 50,
            "rvol_threshold": 2.5,
            "decay_factor": 15,
            "bias_cap": 25,
            "max_gate_atr": 0.8,
            "min_gate_atr": 0.3,

            "score_floor": 65,
            "top_n_cap": 10,
            "ers_reject_normal": 60,
            "ers_reject_trend": 55,
            "ers_degrade_normal": 75,
            "ers_degrade_trend": 70,
            "unlock_threshold": 3,
            "base_capital": 100000,              # [V31 GAP#2] User-configurable base capital
            "max_capital_pct_per_trade": 0.20,    # [V31 GAP#2] Never more than 20% in one trade
        }
        
        # [PHASE 94]: Hard memory/concurrency constraints
        self.CONFIG.update({
            "max_concurrent_jobs": 2,
            "concurrency": 25,  # Max tasks
            "chunk_size": 25,   # Reduced size per chunk
            "throttle_ms": 100  # Phase 94: Soft throttle between symbol chunks
        })
        
        self._semaphore = None
        self.job_states = {}

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
        self._load_persistence_cache()
        self.execution_profile = {} # Slippage feedback loop

    async def _get_index_context(self):
        """[V13] Elite Market Regime & State Synchronization."""
        try:
            # 1. FETCH NIFTY DATA
            # [V31 GAP#7 FIX] Use 15m data for regime detection (was 5m = extremely noisy)
            # ADX 14 on 5m = 70 minutes of data — single chop zone flips regime
            # ADX 14 on 15m = 210 minutes (3.5 hours) — much more stable
            nifty_df = await market_service.get_ohlc("^NSEI", period="5d", interval="15m")
            if nifty_df is None or nifty_df.empty: 
                return self.system_state
            
            close = nifty_df['close'].iloc[-1]
            vwap = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap(nifty_df)
            ad_ratio = await market_service.get_advance_decline_ratio()
            
            # [V14] FETCH INDIA VIX
            market_status = await market_service.get_market_status()
            # [V26 V6-FIX 1] Defensive Fail-Closed (15 to 25)
            india_vix = market_status.get("india_vix", 25.0)

            # 2. ADX STABILITY (6-Candle Check for Hysteresis)
            adx_series = ta_intraday.ADXIndicator(high=nifty_df['high'], low=nifty_df['low'], close=nifty_df['close']).adx()
            curr_adx = adx_series.iloc[-1]
            adx_14_ma = adx_series.iloc[-6:].mean()  # 6-candle smoothed ADX
            
            # 3. REGIME DETECTION WITH HYSTERESIS
            prev_regime = self.system_state.get("regime", "Mixed")
            
            # Calculate true day return (from previous day close, or today's open if 1 day available)
            unique_dates = pd.Series(nifty_df.index.date).unique()
            if len(unique_dates) > 1:
                prev_date = unique_dates[-2]
                prev_close = nifty_df[nifty_df.index.date == prev_date]['close'].iloc[-1]
                day_ret = (close - prev_close) / prev_close
            else:
                today_open = nifty_df['open'].iloc[0]
                day_ret = (close - today_open) / today_open
            
            regime = prev_regime
            if prev_regime == "Trend":
                # Only switch out of Trend if BOTH current AND smoothed ADX drop below 20
                if curr_adx < 18 and adx_14_ma < 20 and abs(day_ret) < 0.002: 
                    regime = "Range"
            else: # Range or Mixed
                # Only enter Trend if BOTH agree
                if (curr_adx > 25 and adx_14_ma > 22) or abs(day_ret) > 0.004: 
                    regime = "Trend"

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
                    
            # Check specific sector momentum correlation
            sector_momentum_stall = False
            if len(nifty_df) >= 3:
                sector_momentum_stall = float(nifty_df['high'].iloc[-1]) < float(nifty_df['high'].iloc[-3])

            self.system_state.update({
                "regime": regime,
                "regime_strength": strength,
                "regime_weight": weight,
                "day_change_pct": round(day_ret * 100, 2),
                "ad_ratio": ad_ratio,
                "nifty_close": close,
                "nifty_vwap": vwap,
                "india_vix": india_vix,
                "sector_momentum_stall": sector_momentum_stall
            })
            
            return {
                "day_change_pct": round(day_ret * 100, 2),
                "india_vix": india_vix,
                "regime": regime,
                "regime_strength": strength,
                "market_trend": "BULLISH" if day_ret > 0.003 else ("BEARISH" if day_ret < -0.003 else "NEUTRAL"),
                "sector_momentum_stall": sector_momentum_stall,
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
        vix = self.system_state.get("india_vix", 25.0)  # V6 Fail-Closed
        
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
            kite_depth = None  # [AUDIT GAP-C] Kite Level-2 order flow data
            if pulse_data and sym in pulse_data:
                item = pulse_data[sym]
                if isinstance(item, pd.DataFrame): df_15m = item
                elif isinstance(item, dict):
                    df_15m = item.get("15m"); df_1h = item.get("1h")
                    # [V36 LTP FIX] Use live price from get_batch_prices(), not stale 15m candle close
                    # OLD: real_price = df_15m['close'].iloc[-1] — up to 15 minutes stale
                    # NEW: Use item["price"] (actual LTP) with candle close as fallback
                    live_price = item.get("price", 0.0)
                    if live_price and live_price > 0:
                        real_price = float(live_price)
                    # [AUDIT GAP-C] Extract Kite market depth if available
                    kite_depth = item.get("kite_depth")
                if real_price == 0.0 and df_15m is not None and not df_15m.empty:
                    real_price = float(df_15m['close'].iloc[-1])  # Fallback only
            else:
                df_15m = await market_service.get_ohlc(sym, period="7d", interval="15m")
                pinfo = await market_service.get_live_price(sym)
                real_price = pinfo.get("price", 0.0)

            if df_15m is None or df_15m.empty or len(df_15m) < 20:
                return {"symbol": sym, "skip_reason": "Data Failure"}

            # [V24 FIX #3] Kite Tradability Gate — skip stocks blocked for intraday on Zerodha
            # Prevents wasting scan capacity on CNC-only stocks that cannot be MIS traded
            kite_status = kite_service.get_tradability(sym)
            if kite_status.get("is_kite_restricted"):
                return {"symbol": sym, "skip_reason": f"Kite Restricted ({kite_status.get('reason', 'CNC Only')})"}

            # [V21.1 FIX] Minimum candle enforcement for indicator validity
            MIN_CANDLES_15M = 100  # ~4 trading days (sufficient for EMA50 + RSI14)
            if len(df_15m) < MIN_CANDLES_15M:
                return {"symbol": sym, "skip_reason": f"Insufficient 15m Data ({len(df_15m)}/{MIN_CANDLES_15M} candles)"}

            # INDICATOR INTEGRITY GUARD
            indicators = self._get_indicators(df_15m, df_1h)
            # [V18 FIX #8] Null guard for indicators
            if indicators is None:
                return {"symbol": sym, "skip_reason": "Indicator Computation Failed"}
            guard = ta_intraday.IntradayTechnicalAnalysis.indicator_integrity_guard(df_15m, indicators)
            if guard["status"] == "safe_skip":
                return {"symbol": sym, "skip_reason": guard["reason"]}
                
            # F21 FIX: Earnings Calendar block
            # Prevent entering stocks right before or during volatile earnings events
            from app.services.earnings_service import earnings_service
            if earnings_service.is_in_earnings_window(sym):
                return {"symbol": sym, "skip_reason": "Earnings Risk Window"}

            # [V33 GAP#1 FIX] Removed duplicate detect_pullback_entry_v45() call
            # OLD: Called V4.5 here with wrong context (global_index_ctx), read phantom flags
            #      (hv_reclaim, squeeze_detected, stop_hunt_reversal) that V4.5 doesn't return.
            #      Then called V4.5 AGAIN in L2 with correct context. = ~200ms wasted per stock.
            # NEW: Use indicators dict directly for flags. V4.5 only called once in L2.
            patterns = {}
            
            # [AUDIT GAP-C] Inject Kite market depth into indicators for L2 confluence
            if kite_depth:
                indicators["kite_depth"] = kite_depth
            
            # --- L2: SCORING ENGINE ---
            l1_score, l1_data = self._run_layer1(indicators)
            indicators["l1_score"] = l1_score
            l2_score, l2_data = self._run_layer2(indicators, df_15m)
            
            # [V17] Beta-Adjusted RS Alpha (Stock vs Index)
            index_rets = global_index_ctx.get("15m_returns", pd.Series())
            stock_rets = df_15m['close'].pct_change().dropna()
            rs_alpha = ta_intraday.IntradayTechnicalAnalysis.calculate_relative_strength_alpha(stock_rets, index_rets)
            
            # [V18 FIX #15] Single RS contribution — no double counting
            rs_contribution = max(min(rs_alpha * 1000, 15), -15)
            is_short_alpha = "SHORT" in l2_data.get("mode", "NONE")
            if is_short_alpha:
                if rs_contribution < 0:
                    l2_data.setdefault("reasons", []).append({"text": "Alpha: Weak Relative Strength vs Index (Short Confirmation)", "impact": int(abs(rs_contribution))})
                    rs_contribution = abs(rs_contribution)
                elif rs_contribution > 0:
                    l2_data.setdefault("reasons", []).append({"text": "Penalty: Strong Relative Strength vs Index (Short Risk)", "impact": -int(rs_contribution)})
                    rs_contribution = -rs_contribution
            else:
                if rs_contribution > 0:
                    l2_data.setdefault("reasons", []).append({"text": "Alpha: Relative Strength vs Index", "impact": int(rs_contribution)})
                elif rs_contribution < 0:
                    l2_data.setdefault("reasons", []).append({"text": "Penalty: Weak Relative Strength vs Index", "impact": int(rs_contribution)})
            
            # [V19 APEX-A] MULTI-TIMEFRAME CONFLUENCE GATE
            # REMOVED: mtf_bonus was causing double-counting of the 1H Trend Up L2 booster.
            
            # [V17] SECTOR HEAT GATING (Structural Filter)
            sector_boost = 0
            sector = market_service.get_sector_for_symbol(sym)
            heat = 0.0
            # [V23 FIX #2] Only apply sector gating for mapped sectors, not "General"
            # OLD: 95% of stocks (mapped to "General") got 0 heat, giving structural disadvantage
            if sector_heat and sector != "General":
                heat = sector_heat.get(sector, 0.0)
                # [V36 GAP#6 FIX] Converted hard reject to penalty — sector rotation alpha plays
                # (strong stock in weak sector) are the highest-alpha intraday setups
                # OLD: heat < -0.005 → hard return (killed stock before L2 scoring)
                # NEW: Negative heat becomes a negative sector_boost, handled by L3 regime penalties
                if is_short_alpha:
                    if heat < -0.005:
                        sector_boost = min(10, abs(heat) * 1000)
                        l2_data.setdefault("reasons", []).append({"text": "Alpha: Weak Sector Catalyst (Short)", "impact": round(sector_boost, 1)})
                    elif heat > 0:
                        sector_boost = -10
                        l2_data.setdefault("reasons", []).append({"text": "Penalty: Strong Sector Heat vs Short", "impact": sector_boost})
                else:
                    if heat < -0.005:
                        sector_boost = -10  # Penalty instead of hard reject
                        l2_data.setdefault("reasons", []).append({"text": "Penalty: Weak Sector Heat", "impact": sector_boost})
                    elif heat > 0:
                        # Scale boost: 5 pts for 0.5% heat, max 10 pts
                        sector_boost = min(10, heat * 1000)
                        l2_data.setdefault("reasons", []).append({"text": "Alpha: Sector Heat Catalyst", "impact": round(sector_boost, 1)})
            
            # [V19 APEX-F] SECTOR ROTATION ALPHA
            # Stock outperforming a hot sector = institutional rotation play
            rotation_boost = 0
            if is_short_alpha:
                if rs_alpha < -0.002 and heat < -0.005:
                    rotation_boost = min(8, abs(heat) * 800)
                    l2_data.setdefault("reasons", []).append({"text": "Alpha: Institutional Sector Rotation (Short)", "impact": round(rotation_boost, 1)})
            else:
                if rs_alpha > 0.002 and heat > 0.005:
                    rotation_boost = min(8, heat * 800)  # +4 for 0.5% heat, +8 for 1%+
                    l2_data.setdefault("reasons", []).append({"text": "Alpha: Institutional Sector Rotation", "impact": round(rotation_boost, 1)})
            
            # [AUDIT GAP#3 FIX] Cap total environmental alpha to ±20 to prevent score inflation
            # Without this cap, RS(+15) + Sector(+10) + Rotation(+8) = +33 can push a bad technical
            # setup (score 45) into Pioneer Prime territory (78+). The base technical L1+L2 must carry
            # the signal — environmental alpha is confirmation, not the primary edge.
            environmental_alpha = rs_contribution + sector_boost + rotation_boost
            capped_alpha = max(min(environmental_alpha, 20), -20)
            base_score = max(0, min(100, l1_score + l2_score + capped_alpha))
            
            # F21 FIX: Inject Daily Macro Trend Data BEFORE Level 3 execution
            df_1d = pulse_data.get(sym, {}).get("1d") if pulse_data else None
            if df_1d is not None and not df_1d.empty and len(df_1d) >= 5:
                ema20_1d = EMAIndicator(close=df_1d['close'], window=20).ema_indicator().iloc[-1]
                indicators["is_1d_bullish"] = real_price > ema20_1d
            else:
                indicators["is_1d_bullish"] = None
            
            # [V42] Daily Consolidation Breakout Detection
            # Stocks stuck in a tight range for 20 days that break out today = explosive 5%+ runners
            indicators["daily_breakout"] = {}
            if df_1d is not None and not df_1d.empty and len(df_1d) >= 20:
                try:
                    daily_high_20 = float(df_1d['high'].tail(20).max())
                    daily_low_20 = float(df_1d['low'].tail(20).min())
                    range_pct = (daily_high_20 - daily_low_20) / max(daily_low_20, 1e-6)
                    is_tight_range = range_pct < 0.15
                    is_breaking_out = real_price > daily_high_20 * 1.002
                    indicators["daily_breakout"] = {
                        "is_consolidation_breakout": is_tight_range and is_breaking_out,
                        "range_pct": round(range_pct * 100, 1),
                        "breakout_distance": round((real_price / max(daily_high_20, 1e-6) - 1) * 100, 2)
                    }
                except Exception:
                    pass
                
            # [V18 FIX #7] L3: PENALTY ENGINE — re-integrated into scoring
            liq = liquidity_service.get_liquidity(sym)
            l3_penalty, l3_data = self._run_layer3(indicators, df_15m, global_index_ctx, l2_data, liq)
            base_score = max(0, min(100, base_score - l3_penalty))
            
            # [V42] Mega-Cap Pioneer Prime Suppression
            # Stocks priced above ₹2,000 cannot physically deliver 5%+ intraday moves
            # due to institutional depth. Cap them below Pioneer Prime threshold.
            if real_price > 2000 and base_score > 78:
                base_score = 78
            
            # [V42] RVOL Gate for Pioneer Prime
            # Pioneer Prime (85+) requires institutional-grade volume confirmation
            # RVOL 1.5 = above average (fine for BUY), RVOL 2.5+ = institutional aggression (required for PRIME)
            _rvol_for_gate = indicators.get("rvol", 0)
            if base_score >= 85 and _rvol_for_gate < 2.5:
                base_score = min(base_score, 82)
            
            # --- L3: EXECUTION GATING ---
            # 1. Freshness Guard
            # [V21.1 FIX] Only apply the 10-minute staleness check if the Indian market is actually open.
            ist = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            is_market_open = (9 * 60 + 15 <= now_ist.hour * 60 + now_ist.minute <= 15 * 60 + 30) and (now_ist.weekday() < 5)
            
            # [V24 FIX #4] Use IST-consistent comparison for staleness check
            # OLD: Compared datetime.utcnow() with potentially TZ-localized IST timestamps = 5.5h error
            # NEW: Convert both sides to IST before comparison
            last_candle_ts = df_15m.index[-1]
            if hasattr(last_candle_ts, 'tz') and last_candle_ts.tz is not None:
                last_candle_ist = last_candle_ts.to_pydatetime().astimezone(ist)
            else:
                # Naive timestamp — assume UTC (Yahoo default), convert to IST
                last_candle_ist = pytz.utc.localize(last_candle_ts.to_pydatetime()).astimezone(ist)
            staleness_seconds = (now_ist - last_candle_ist).total_seconds()
            if is_market_open and staleness_seconds > 600: # 10m limit
                return {"symbol": sym, "skip_reason": "Stale Data (>10m)"}
            
            # 2. Volatility Kill-Switch
            atr_pct = indicators['atr'] / real_price
            if atr_pct > 0.05: # Extreme volatility reject
                return {"symbol": sym, "skip_reason": "Extreme Volatility (ATR > 5%)"}
            
            # [V21.3 FIX] Macro Crash Guard (Nifty Intraday Trend)
            # If the broader market is crashing (>1% down), only allow exceptional, high-relative-volume setups.
            day_change_pct = global_index_ctx.get("day_change_pct", 0.0)
            is_exec_short = "SHORT" in l2_data.get("mode", "NONE")
            if day_change_pct <= -1.0 and not is_exec_short and indicators.get("rvol", 0) < 3.0:
                return {"symbol": sym, "skip_reason": f"Macro Crash Guard (Nifty {day_change_pct}%, RVOL < 3.0)"}
            
            # [V14] 3. Multi-Day Weekly Resistance Hard Filter
            # Automatically reject Longs if price is within 0.5% of 5-Day High
            if df_1d is not None and not df_1d.empty and len(df_1d) >= 5:
                weekly_high = float(df_1d['high'].tail(5).max())
                weekly_low = float(df_1d['low'].tail(5).min())
                # [V23 FIX #3] Breakout Bypass: Don't kill high-RVOL breakout candidates
                # OLD: Hard rejected ALL stocks near 5D high, making BREAKOUT alpha mode dead
                # NEW: Allow through if volume is institutional (RVOL > 2.0) AND structure is intact
                is_potential_breakout = indicators.get("rvol", 0) > 2.0 and indicators.get("structure_ok", False)
                if is_exec_short:
                    if real_price <= weekly_low * 1.003 and real_price > weekly_low * 0.997 and not is_potential_breakout:
                        return {"symbol": sym, "skip_reason": "Multi-Day Support (Near 5D Low)"}
                else:
                    if real_price >= weekly_high * 0.997 and real_price < weekly_high * 1.002 and not is_potential_breakout:
                        return {"symbol": sym, "skip_reason": "Multi-Day Resistance (Near 5D High)"}
                
            # 4. ERS Terminal Gating
            # [V24 FIX #2] ERS now uses Kite tradability data instead of phantom default-100
            # OLD: indicators.get("ers_score", 100) → always 100, gate never fired
            # NEW: Use kite multiplier as proxy for execution readiness
            kite_mult = kite_status.get("multiplier", 1.0)
            # Map multiplier to ERS: mult >= 5x = 100 (great), 2-5x = 80, 1-2x = 50, <1 = 0
            ers_score = 100 if kite_mult >= 5.0 else (80 if kite_mult >= 2.0 else (50 if kite_mult > 1.0 else 0))
            ers_gates = self._get_adaptive_ers_threshold()
            if ers_score < ers_gates["reject"]:
                return {"symbol": sym, "skip_reason": f"Adaptive ERS Reject ({ers_score} < {ers_gates['reject']})"}
            
            # [V36 GAP#1+2 FIX] VWAP chase penalty MOVED INSIDE _run_layer3()
            # OLD: Applied post-L3, bypassing the L3 penalty cap (MAX_L3_PENALTY=50-60)
            #      AND penalized MOMENTUM stocks whose alpha IS VWAP extension — circular logic
            # NEW: Inside L3, subject to cap, exempts MOMENTUM/BREAKOUT/OPENING_DRIVE
                
            # 5. 9:30 Trap
            # [V35 GAP#2 FIX] V33 emptied patterns dict → trap guard always fired, killing
            # ALL stocks during 9:15-9:30 (the highest-probability window for gap-and-go/ORB).
            # NEW: Use indicator-level data instead of phantom patterns dict
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            if ist_now.hour == 9 and ist_now.minute < 30:
                orb_status = indicators.get("orb", {}).get("status", "Inside")
                has_conviction = indicators.get("smart_gate_bypass", False)
                is_orb_break = orb_status in ["Breakout", "Early Breakout"]
                if not has_conviction and not is_orb_break and indicators.get("rvol", 0) < 2.0:
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
                r_type = "negative" if float(r_obj.get("impact", 0)) < 0 else "positive"
                reasons.append({"text": r_obj["text"], "type": r_type, "layer": 1, "impact": r_obj["impact"]})
            for r_obj in l2_data.get("reasons", []):
                r_type = "negative" if float(r_obj.get("impact", 0)) < 0 else "positive"
                reasons.append({"text": r_obj["text"], "type": r_type, "layer": 2, "impact": r_obj["impact"]})
            for r_obj in l3_data.get("reasons", []):
                # L3 reasons are always penalties
                reasons.append({"text": r_obj["text"], "type": "negative", "layer": 3, "impact": r_obj["impact"]})

            groups = {
                "DNA (40%)": {"score": l1_score, "max": 40, "details": [r for r in reasons if r["layer"] == 1]},
                "Alpha Edge (60%)": {"score": l2_score, "max": 60, "details": [r for r in reasons if r["layer"] == 2]},
                "Safeguards (L3)": {"score": -l3_penalty, "max": 0, "details": [r for r in reasons if r["layer"] == 3]}
            }

            signal = self._get_signal(base_score, l2_data.get("mode", "NONE"))
            verdict = "PIONEER PRIME" if base_score >= 85 else "Standard"

            # [V19 APEX-H] STRUCTURAL RISK MANAGEMENT
            # [V26 V6-FIX 1] Defensive Fail-Closed (15 to 25)
            india_vix = global_index_ctx.get("india_vix", 25)
            atr = indicators.get("atr", 0)
            
            # Stop-Loss: Symmetrical ATR & Structural evaluation
            atr_sl_dist = max(atr * (2.0 if india_vix > 20 else 1.5), real_price * 0.005)
            alpha_mode = l2_data.get("mode", "NONE")
            is_short = "SHORT" in alpha_mode
            atr_sl = round(real_price + atr_sl_dist if is_short else real_price - atr_sl_dist, 2)
            
            if df_15m is not None and len(df_15m) >= 6:
                max_sl_distance = min(real_price * 0.015, atr * 3.0)  # [GAP #5 FIX] Cap at 1.5% or 3 ATR to preserve RR
                if is_short:
                    structural_sl = round(float(df_15m['high'].iloc[-6:].max()), 2)
                    structural_sl = min(structural_sl, real_price + max_sl_distance)
                    stop_loss = min(structural_sl, atr_sl)  # Lower is tighter for shorts
                else:
                    structural_sl = round(float(df_15m['low'].iloc[-6:].min()), 2)
                    structural_sl = max(structural_sl, real_price - max_sl_distance)
                    stop_loss = max(structural_sl, atr_sl)  # Higher is tighter for longs
            else:
                stop_loss = atr_sl
                
            # F7 FIX: Correct OPENING_DRIVE stop-loss logic
            if alpha_mode == "OPENING_DRIVE" and df_15m is not None:
                today_mask = df_15m.index.date == df_15m.index[-1].date()
                if today_mask.sum() > 0:
                    if is_short:
                        day_high = round(float(df_15m[today_mask]['high'].max()), 2)
                        orb_min_sl = round(real_price * 1.003, 2)
                        orb_max_sl = round(min(real_price * 1.03, real_price + atr * 3), 2)
                        stop_loss = max(orb_min_sl, min(orb_max_sl, day_high))
                    else:
                        day_low = round(float(df_15m[today_mask]['low'].min()), 2)
                        orb_min_sl = round(real_price * 0.997, 2)
                        orb_max_sl = round(max(real_price * 0.97, real_price - atr * 3), 2)
                        stop_loss = min(orb_min_sl, max(orb_max_sl, day_low))
                    
            stop_loss = l2_data.get("dynamic_zones", {}).get("stop_loss") or stop_loss
            
            # [V28 V8-FIX] Time-Weighted Edge Decay (Target Scaling)
            try:
                # [AUDIT GAP#5 FIX] Time decay must use candle timestamp, not wall clock.
                # If we scan on a Sunday or backtest, wall clock time breaks the logic.
                if df_15m is not None and not df_15m.empty:
                    last_ts = df_15m.index[-1]
                    if hasattr(last_ts, 'tzinfo') and last_ts.tzinfo is None:
                        last_ts = last_ts.tz_localize('UTC').tz_convert('Asia/Kolkata')
                    elif hasattr(last_ts, 'tz_convert'):
                        last_ts = last_ts.tz_convert('Asia/Kolkata')
                    current_hour = last_ts.hour + (last_ts.minute / 60.0)
                else:
                    now_ist = datetime.now(pytz.timezone('Asia/Kolkata'))
                    current_hour = now_ist.hour + (now_ist.minute / 60.0)
                
                time_decay_factor = 1.0
                if current_hour > 10.0:
                    # [V40 GAP#2 FIX] Slower decay (0.10/hr vs 0.12/hr), higher floor (0.5 vs 0.4)
                    # Old rate created sub-1.0 RR targets after 12:30 PM → negative expectancy
                    time_decay_factor = max(0.5, 1.0 - ((current_hour - 10.0) * 0.10))
            except Exception as e:
                print(f"️ Time decay fallback error: {e}")
                time_decay_factor = 1.0

            # Target: Nearest resistance/support level, capped by ATR extension
            atr_target_dist = max((atr * time_decay_factor) * (3.0 if india_vix > 20 else 2.0), real_price * 0.01)
            # [AUDIT GAP#2 FIX] REMOVED artificial 1.3 RR floor — this was extending the target past structural
            # resistance, turning winning trades into stop-outs. The market doesn't care about our math.
            # If structural resistance is at 1.0 RR, forcing the target to 1.3 RR just means we never hit it.
            # Instead, we validate ACTUAL structural RR after target calculation and reject if < 1.2.
            atr_target = round(real_price - atr_target_dist if is_short else real_price + atr_target_dist, 2)
            
            pivot_data = indicators.get("pivots", {})
            vwap_val = indicators.get("vwap_val", 0)
            
            if is_short:
                valid_res = [v for v in pivot_data.values() if isinstance(v, (int, float)) and v < real_price * 0.998]
                if vwap_val < real_price * 0.998: valid_res.append(vwap_val)
                if valid_res:
                    nearest_res = max(valid_res) # Highest support below price
                    target = round(max(nearest_res, real_price - (atr_target_dist * 1.2)), 2) if nearest_res < real_price * 0.995 else atr_target
                else: target = atr_target
            else:
                valid_res = [v for v in pivot_data.values() if isinstance(v, (int, float)) and v > real_price * 1.002]
                if vwap_val > real_price * 1.002: valid_res.append(vwap_val)
                if valid_res:
                    nearest_res = min(valid_res)
                    target = round(min(nearest_res, real_price + (atr_target_dist * 1.2)), 2) if nearest_res > real_price * 1.005 else atr_target
                else: target = atr_target
                
            target = l2_data.get("dynamic_zones", {}).get("target") or target

            # [V21] Liquidity Ceiling Compression
            adv20_dollar = adv20 * real_price
            if max_value > (adv20_dollar * 0.05):
                target = round(real_price + ((target - real_price) * 0.75), 2)
            
            # [AUDIT GAP#2 FIX] Structural RR Rejection Gate
            # Validates the ACTUAL target/stop distance AFTER all structural adjustments.
            # If the trade offers < 1.2 RR after deducting execution costs (~0.08%), reject it.
            _structural_reward = abs(target - real_price) - (real_price * 0.0008)  # Deduct round-trip costs
            _structural_risk = abs(stop_loss - real_price)  # [FIX] Use actual calculated stop-loss, not generic ATR
            _structural_rr = _structural_reward / max(_structural_risk, 1e-6)
            if _structural_rr < 1.2:
                return {"symbol": sym, "skip_reason": f"Poor Structural RR ({_structural_rr:.2f} < 1.2). Artificial extension prevented."}
            
            # [V24 V3-FIX 2] Execution Edge: Pin limit orders on defensive setups
            # [V40 GAP#1 FIX] Realistic slippage model calibrated from NSE microstructure
            # PULLBACK/SHORT_PULLBACK: Limit order pinning → near-zero slippage (existing logic)
            # MOMENTUM/BREAKOUT/OPENING_DRIVE: Market order chase → adverse slippage by liquidity tier
            # High (>₹50Cr): 0.05%, Moderate (₹10-50Cr): 0.12%, Low (<₹10Cr): 0.25%
            _SLIPPAGE_MAP = {"High": 0.0005, "Moderate": 0.0012, "Low": 0.0025, "Very Low": 0.0035, "Unknown": 0.0015}
            _slip_pct = _SLIPPAGE_MAP.get(liq_level, 0.0015)
            
            ideal_entry = real_price
            # [AUDIT GAP#4 FIX] Zone Execution
            # If price is ALREADY within 0.5 ATR of the moving average support, execute at Market.
            # If price has escaped the zone (bolted before we could enter), reject.
            if alpha_mode == "PULLBACK":
                ideal_entry = round(real_price * (1 + _slip_pct), 2)  # Market execution with slippage
                # Use L2 ATR for normalization. If it bounced more than 0.75 ATR from entry, it escaped.
                if (real_price - stop_loss) / max(atr, 1e-6) > 2.0:
                     return {"symbol": sym, "skip_reason": f"Pullback price escaped execution zone (>2.0 ATR from SL)"}
            elif alpha_mode == "SHORT_PULLBACK":
                ideal_entry = round(real_price * (1 - _slip_pct), 2)  # Market execution with slippage
                if (stop_loss - real_price) / max(atr, 1e-6) > 2.0:
                     return {"symbol": sym, "skip_reason": f"Short Pullback price escaped execution zone (>2.0 ATR from SL)"}
            else:
                # Market order entry: apply adverse slippage (buy higher, short lower)
                if is_short:
                    ideal_entry = round(real_price * (1 - _slip_pct), 2)
                else:
                    ideal_entry = round(real_price * (1 + _slip_pct), 2)

            # [V29 V9-FIX 1] sl_dist now uses ideal_entry instead of real_price to correctly represent limit risk
            # [V31 GAP#5 FIX] Enforce minimum 0.3% or 0.5 ATR stop distance to prevent infinite position sizes
            # OLD: max(..., 0.01) — for a ₹100 stock, 0.01 = 0.01% → position_size = risk_amount / 0.01 = absurd
            min_sl_dist = max(real_price * 0.003, atr * 0.5)
            
            # [V42 FIX] Re-anchor Stop Loss to Ideal Entry
            # Prevents limit pins from placing Entry *inside* the stop loss zone (SL > Entry for longs)
            if is_short:
                stop_loss = max(stop_loss, ideal_entry + min_sl_dist)
            else:
                stop_loss = min(stop_loss, ideal_entry - min_sl_dist)
                
            sl_dist = abs(ideal_entry - stop_loss)
            
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
            
            # [V31 GAP#2 FIX] Use configurable capital instead of hardcoded ₹1L
            capital = self.CONFIG["base_capital"]
            # [V36 GAP#5 FIX] Removed time_decay_factor from risk_amount
            # OLD: risk_amount * time_decay_factor — double-compressed RR at EOD
            #      (target already scaled by time_decay, position size also scaled = both sides shrink)
            # NEW: Time decay only affects target, not position sizing
            risk_amount = (capital * risk_pct) / beta_proxy

            # [V31 GAP#2 FIX] Hard ceiling: never more than 20% of capital in one trade
            max_position_value = capital * self.CONFIG["max_capital_pct_per_trade"]


            return {
                "symbol": sym,
                "price": round(real_price, 2),
                "score": round(base_score, 1),
                "priority": priority,
                "rs_alpha": round(rs_alpha, 4),
                "regime": regime,
                "mode": l2_data.get("mode", "NONE"),
                "flags": {
                    # [V33 GAP#1 FIX] Source flags from actual computed data, not phantom V4.5 returns
                    "HV_RECLAIM": indicators.get("smart_gate_bypass", False),  # Equivalent conviction signal
                    "SQUEEZE": bool(indicators.get("squeeze", {}).get("is_squeeze")),  # From L2 confluence
                    "STOP_HUNT": bool(indicators.get("accumulation", {}).get("is_sweep_confirmed")),  # From L2
                    "VACUUM": False,  # Deprecated — no longer computed
                    "FOOTPRINT": indicators.get("footprint", 0),
                    "MTF_ALIGNED": indicators.get("ema_1h_trend_up") is True and indicators.get("is_1d_bullish") is True,
                    "PERSISTENCE": persistence_count
                },
                "verdict": verdict,
                "signal": signal,
                "reasons": reasons,
                "groups": groups,
                "entry": round(ideal_entry, 2), # V3-FIX 2 applied here
                "target": target,
                "stop_loss": stop_loss,
                # [V40 GAP#12 FIX] Deduct round-trip execution costs (brokerage+STT+stamps ≈ 0.08%)
                "rr_ratio": round(((target - ideal_entry) - (ideal_entry * 0.0008)) / sl_dist, 2) if sl_dist > 0 else 0,
                # [V33 GAP#4 FIX] Increased ADV20 stealth from 1% to 2% — institutional standard for liquid stocks
                "position_size": min(
                    int(risk_amount / sl_dist),
                    int(max_position_value / max(real_price, 1)),
                    max(int(adv20 * 0.02), 1) if adv20 > 0 else int(max_position_value / max(real_price, 1))
                ),
                "alpha_mode": l2_data.get("mode", "NONE"),
                "liquidity": {
                    "level": liq_level,
                    "adv20": adv20,
                    "max_stealth_buy_qty": max_qty,
                    "max_stealth_buy_value": max_value
                },
                "timestamp": datetime.now(pytz.timezone('Asia/Kolkata')).isoformat()
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"symbol": sym, "skip_reason": f"System Error: {str(e)}"}

    def _get_indicators(self, df_15m, df_1h):
        ind_15m = self._compute_indicators(df_15m)
        if ind_15m is None: return None
        
        # [V23 FIX #5] Proper df_1h null guard — bare except on None.attribute was hiding infra failures
        ema_1h_trend_up = None
        # [V33 GAP#6 FIX] Default to None instead of True — True suppresses the -15 L3 penalty
        is_1h_momentum_bullish = None
        if df_1h is not None and not df_1h.empty:
            try:
                ema_1h_series = EMAIndicator(close=df_1h['close'], window=20).ema_indicator()
                if len(ema_1h_series) >= 2:
                    ema_1h = ema_1h_series.iloc[-1]
                    ema_1h_prev = ema_1h_series.iloc[-2]
                    ema_1h_trend_up = ema_1h > ema_1h_prev
                    
                # [V24 V3-FIX 3] 1H MACD Momentum Matrix
                macd_1ha = EMAIndicator(close=df_1h['close'], window=12).ema_indicator()
                macd_1hb = EMAIndicator(close=df_1h['close'], window=26).ema_indicator()
                macd_1h_line = macd_1ha - macd_1hb
                macd_1h_signal = EMAIndicator(close=macd_1h_line, window=9).ema_indicator()
                if len(macd_1h_line) >= 1 and len(macd_1h_signal) >= 1:
                    is_1h_momentum_bullish = bool(macd_1h_line.iloc[-1] > macd_1h_signal.iloc[-1])
            except Exception:
                pass  # ema_1h_trend_up stays None
            
        return {**ind_15m, "ema_1h_trend_up": ema_1h_trend_up, "is_1h_momentum_bullish": is_1h_momentum_bullish}

    def _compute_indicators(self, df: pd.DataFrame):
        # R4-6 FIX: Capture symbol BEFORE copy/tail — .tail() may not preserve .attrs
        symbol = df.attrs.get("symbol", "")
        
        # [V24 V3-FIX 1] Memory Optimization: Zero-Copy DataFrame Slicing
        # OLD: df = df.copy().tail(210) — heavy memory allocation per stock, fragmented heap
        # NEW: use shallow iloc slice. Only copy if we actually need to mutate NaNs.
        df = df.iloc[-210:]
        if df.isnull().values.any() or (df == 0).values.any():
            df = df.copy()

        # F15: Single-pass column array materialization to avoid 150k redundant checks
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns and isinstance(df[col], pd.DataFrame):
                df[col] = df[col].iloc[:, 0]
        df.attrs["_series_ensured"] = True
        
        # Hardness Gate: Prevent library crashes (e.g. TA logic) on low data
        if len(df) < 20:
            return None
            
        # FIX V21: DataFrame NaN Contamination Protocol
        # [V21.1 FIX] Only replace zeros in PRICE columns (O/H/L/C cannot be 0 for listed stocks).
        # Volume CAN be legitimately 0 (circuit halt, pre-market). Replacing it would inflate RVOL.
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = df[col].replace(0, np.nan)
        df.ffill(inplace=True)
        df.bfill(inplace=True)
            
        price = df['close'].iloc[-1]
        
        # [V34 GAP#2 FIX] Compute VWAP via analyze_vwap_advanced() ONCE
        # OLD: Called calculate_vwap_series() here, then analyze_vwap_advanced() again at L853
        #      which internally calls calculate_vwap_series() → double VWAP computation per stock
        # NEW: Single call, extract both scalar and oscillation flag
        try:
            vwap_ctx = ta_intraday.IntradayTechnicalAnalysis.analyze_vwap_advanced(df)
            vwap = vwap_ctx.get("vwap_val", df['close'].iloc[-1])
        except Exception:
            vwap_ctx = {"oscillating": False, "vwap_val": df['close'].iloc[-1]}
            vwap = vwap_ctx["vwap_val"]
            
        # F2 FIX: Time-weighted VWAP reliability score
        if isinstance(df.index, pd.DatetimeIndex) and len(df) > 0:
            last_ts = df.index[-1]
            if hasattr(last_ts, 'hour'):
                session_elapsed = (last_ts.hour - 9) * 60 + last_ts.minute - 15  # mins since 9:15
                # After 4+ hours, VWAP stabilizes and loses discrimination power
                vwap_reliability = max(0.3, 1.0 - (max(0, session_elapsed - 180) / 360))
            else:
                vwap_reliability = 0.7
        else:
            vwap_reliability = 0.7
            
        # Still need the series for pullback proximity checks (L829)
        vwap_series = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap_series(df)
        distance_vwap = ((price - vwap) / vwap) * 100
        
        ema20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
        ema20 = ema20_series.iloc[-1]
        ema50 = EMAIndicator(close=df['close'], window=50).ema_indicator().iloc[-1]
        # FIX H1: Use raw single-candle diff for real-time slope (was rolling(3).mean() = 2-candle lag)
        # [V24 FIX #10] Normalize by price so slope is scale-independent
        # OLD: raw diff — ₹0.1 is significant for ₹100 stock but noise for ₹5000 stock
        # NEW: percentage-normalized slope works identically across all price ranges
        raw_slope = ema20_series.diff().iloc[-1]
        ema_slope = raw_slope / max(price, 1e-6)
        
        avg_vol = df['volume'].rolling(20).mean()
        # [V24 FIX #1] Use COMPLETED candle for RVOL — the last candle is still forming
        # during live scans, accumulating only a fraction of its expected volume.
        # This caused universal near-zero RVOL → false -15 to -25 L3 penalties on ALL stocks.
        # Using iloc[-2] (last completed candle) gives accurate volume measurement.
        if len(df) >= 3:
            current_vol = df['volume'].iloc[-2]  # Last COMPLETED candle
        else:
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
            # [V23 FIX #6] Use MEDIAN of recent diffs to avoid overnight gap contamination
            # OLD: Used last two candles only — if they span overnight, inferred_mins = 1065
            if isinstance(df.index, pd.DatetimeIndex) and len(df.index) >= 2:
                if len(df.index) >= 6:
                    recent_diffs = df.index.to_series().diff().iloc[-5:].dt.total_seconds() / 60
                    valid_diffs = recent_diffs[(recent_diffs >= 1) & (recent_diffs <= 60)]
                    inferred_mins = float(valid_diffs.median()) if len(valid_diffs) > 0 else 15.0
                else:
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
        # [V40 GAP#8 FIX] Use completed candles only (exclude forming candle at -1) to prevent
        # approving breakout structures on candles that haven't closed yet
        if len(df) >= 6:
            recent_highs = df['high'].iloc[-6:-1]
            recent_lows = df['low'].iloc[-6:-1]
            # Higher Low: completed candle low > low from 4 bars ago (upward structure)
            hl_confirmed = df['low'].iloc[-2] > df['low'].iloc[-5]
            # Not making Lower Highs: completed high >= prior high
            no_lower_high = df['high'].iloc[-2] >= df['high'].iloc[-3] * 0.998  # 0.2% tolerance
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
        touched_resistance = False
        if len(df) >= 3:
            for i in range(-3, 0):
                c_low = df['low'].iloc[i]
                c_high = df['high'].iloc[i]
                c_ema20 = ema20_series.iloc[i]
                c_ema9 = ema9_series.iloc[i]
                c_vwap = vwap_series.iloc[i] if len(vwap_series) >= 3 else vwap
                # ATR-normalized: EMA20 within 0.3 ATR, EMA9 within 0.2 ATR, VWAP within 0.15 ATR
                if c_low <= c_ema20 + (atr * 0.3) or c_low <= c_ema9 + (atr * 0.2) or c_low <= c_vwap + (atr * 0.15):
                    touched_support = True
                if c_high >= c_ema20 - (atr * 0.3) or c_high >= c_ema9 - (atr * 0.2) or c_high >= c_vwap - (atr * 0.15):
                    touched_resistance = True
                if touched_support and touched_resistance: break
        else:
            touched_support = low.iloc[-1] <= ema20 + (atr * 0.3)
            touched_resistance = df['high'].iloc[-1] >= ema20 - (atr * 0.3)
            
        trend_resuming = df['close'].iloc[-1] > df['close'].iloc[-2]
        trend_resuming_down = df['close'].iloc[-1] < df['close'].iloc[-2]
        # [V36 GAP#7 FIX] Allow EMA-touch pullbacks (price at or slightly below EMA20)
        # OLD: price > ema20 — excluded the exact EMA20 touch, which is the highest-probability entry
        # NEW: Allow 0.1 ATR tolerance below EMA20 to catch institutional entries at the level
        is_pullback = touched_support and trend_resuming and price > (ema20 - atr * 0.1)
        is_short_pullback = touched_resistance and trend_resuming_down and price < (ema20 + atr * 0.1)
        
        distance_ema = ((price - ema20) / ema20) * 100
        # Dynamic Institutional Exhaustion: Scaled by ATR (3x ATR Band)
        exhaustion_limit = (atr * 3 / price) * 100 if price > 0 else 5.0
        # FIX #3: Changed OR to AND — gap-up stocks were immediately killed by VWAP distance alone
        # A stock that opens 4% above VWAP (gap-and-go) shouldn't be flagged exhausted
        # unless it's ALSO stretched from EMA20. Both conditions must be true.
        # V14.6 FIX: Bi-directional exhaustion (absolute distance)
        # [V32 P8 FIX] Scale exhaustion threshold for volatile stocks
        # OLD: Fixed 2.5 ATR cutoff — too tight for small/mid-caps with 2-3% daily range
        atr_pct_intraday = (atr / max(price, 1)) * 100
        exhaustion_atr_threshold = 3.5 if atr_pct_intraday > 2.0 else 2.5  # Wider gate for volatile stocks
        # [V35 GAP#1 FIX] Use computed threshold instead of hardcoded 3.5
        # OLD: abs(distance_vwap) > 3.5 — volatile stocks never hit exhaustion gate
        is_exhausted = abs(distance_vwap) > exhaustion_atr_threshold and abs(distance_ema) > exhaustion_limit
        
        exhaustion_ctx = ta_intraday.IntradayTechnicalAnalysis.check_exhaustion(df, price)
        
        try:
            mfi = MFIIndicator(high=df['high'], low=df['low'], close=df['close'], volume=df['volume'], window=14).money_flow_index().iloc[-1]
        except Exception:
            mfi = 50.0

        # [V34 GAP#2 FIX] vwap_ctx already computed at L733 — removed duplicate call
        
        # FIX C2: Compute pa_score here so Smart Gate can use it
        # (Same logic as analyze_stock: close in top 20% of candle = aggressive buying)
        last_candle = df.iloc[-1]
        c_range = last_candle['high'] - last_candle['low']
        close_relative = (price - last_candle['low']) / c_range if c_range > 0 else 0.5
        pa_score = 100 if close_relative > 0.8 and rvol > 1.2 else (80 if close_relative > 0.8 else (50 if close_relative > 0.5 else 0))

        # [V23 FIX #13] Smart Gate Revival — was dead code (never populated).
        # Fires when price is below EMA20 but showing strong reversal conviction signals.
        # This enables the +15 L2 boost and reduced L3 penalty for high-conviction reclaims.
        # [V23 FIX #13] Smart Gate Revival & [V38] Short Setup Symmetrical Bypass
        smart_gate_bypass = False
        volume_conviction = rvol > 2.0
        
        if price < ema20:
            # Bullish Reclaim Conviction (close near high, crossing over prev close)
            reclaim_candle = close_relative > 0.8 and price > df['close'].iloc[-2]
            if reclaim_candle and volume_conviction:
                smart_gate_bypass = True
        elif price > ema20:
            # Bearish Breakdown Conviction (close near low, violently dropping below prev close)
            breakdown_candle = close_relative < 0.2 and price < df['close'].iloc[-2]
            if breakdown_candle and volume_conviction:
                smart_gate_bypass = True

        # [V24 FIX #5 & #7] Compute ORB, Gap, and Pivots
        # OLD: These were never computed here, but analyze_stock and L2 Scoring tried to read them,
        # resulting in dead OPENING_DRIVE logic and dead target resistance logic.
        orb_ctx = ta_intraday.IntradayTechnicalAnalysis.detect_orb(df)
        gap_ctx = ta_intraday.IntradayTechnicalAnalysis.analyze_gap(df)
        pivots = ta_intraday.IntradayTechnicalAnalysis.calculate_pivots(df)
        
        # [V31 GAP#10 FIX] Wire unused trend direction and market structure detectors
        # These functions exist in ta_intraday.py but were never called — wasting valuable alpha signals
        trend_dir = ta_intraday.IntradayTechnicalAnalysis.detect_trend_direction(df)
        mkt_struct = ta_intraday.IntradayTechnicalAnalysis.detect_market_structure(df)

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
            "is_short_pullback": is_short_pullback,
            "is_exhausted": is_exhausted,
            "exhaustion": exhaustion_ctx,
            "mfi": mfi,
            "atr": atr,
            "pa_score": pa_score,  # FIX C2: pa_score now populated for Smart Gate
            "smart_gate_bypass": smart_gate_bypass,  # [V23 FIX #13] Revived Smart Gate flag
            "orb": orb_ctx,        # [V24 FIX #5]
            "gap": gap_ctx,        # [V24 FIX #5]
            "pivots": pivots,      # [V24 FIX #7]
            "trend_direction": trend_dir.get("trend_direction_state", "NEUTRAL_TREND"),   # [V31 GAP#10]
            "market_structure": mkt_struct.get("market_structure_state", "NEUTRAL_STRUCTURE"),  # [V31 GAP#10]
            "vwap_oscillating": vwap_ctx.get("oscillating", False),  # [V32 P3]
            "vwap_reclaim": vwap_ctx.get("reclaim", False),  # [V36 GAP#3] VWAP reclaim wired
            "vwap_reliability": vwap_reliability
        }

    def _run_layer1(self, indicators):
        price, ema20, ema_slope = indicators["price"], indicators["ema20"], indicators["ema_slope"]
        distance_vwap, rvol = indicators["distance_vwap"], indicators["rvol"]
        score, reasons = 0, []
        
        is_bearish_structure = price < ema20 and distance_vwap < -0.5
        
        # DNA Recalibration: 10 points per check (Total 40)
        if is_bearish_structure:
            if price < ema20:
                score += 10; reasons.append({"text": "Price below EMA20", "impact": 10})
            if ema_slope < 0:
                score += 10; reasons.append({"text": "EMA20 trending down", "impact": 10})
        else:
            if price > ema20: 
                score += 10; reasons.append({"text": "Price above EMA20", "impact": 10})
            if ema_slope > 0: 
                score += 10; reasons.append({"text": "EMA20 trending up", "impact": 10})
        
        # FIX M2: Corrected VWAP bias tracking (No absolute hacks that turn dropping stocks positive)
        vwap_weight = indicators.get("vwap_reliability", 1.0)
        vwap_pts_near = int(10 * vwap_weight)
        vwap_pts_ext = int(5 * vwap_weight)
        
        atr_pct = (indicators.get("atr", 0) / max(price, 1)) * 100
        vwap_limit = max(atr_pct * 1.5, 0.75)
        
        if 0 <= abs(distance_vwap) < vwap_limit: 
            score += vwap_pts_near; reasons.append({"text": f"Near VWAP (< {vwap_limit:.1f}%)", "impact": vwap_pts_near})
        elif is_bearish_structure and distance_vwap <= -vwap_limit:
            score += vwap_pts_ext; reasons.append({"text": f"Extended below VWAP (Bearish Extension)", "impact": vwap_pts_ext})
        elif not is_bearish_structure and distance_vwap >= vwap_limit: 
            score += vwap_pts_ext; reasons.append({"text": f"Extended from VWAP (> {vwap_limit:.1f}%)", "impact": vwap_pts_ext})
        elif not is_bearish_structure and distance_vwap < 0:
            score -= 5; reasons.append({"text": "Below VWAP (bearish bias)", "impact": -5})
            
        # P3 FIX: Added RVOL 0.8-1.2 tier
        if rvol > 2: 
            score += 10; reasons.append({"text": "High RVOL (institutional volume)", "impact": 10})
        elif rvol > 1.2: 
            score += 6; reasons.append({"text": "Above avg volume", "impact": 6})
        elif rvol > 0.8:
            score += 3; reasons.append({"text": "Normal volume", "impact": 3})
        
        # [V31 GAP#10 FIX] Intraday Trend Direction + Market Structure Bonus
        if is_bearish_structure:
            if indicators.get("trend_direction") == "BEARISH_TREND" and indicators.get("market_structure") == "BEARISH_STRUCTURE":
                score += 5; reasons.append({"text": "Confirmed intraday downtrend (LH/LL)", "impact": 5})
            elif indicators.get("trend_direction") == "BULLISH_TREND":
                score -= 5; reasons.append({"text": "Intraday uptrend contradicting short bias", "impact": -5})
        else:
            if indicators.get("trend_direction") == "BULLISH_TREND" and indicators.get("market_structure") == "BULLISH_STRUCTURE":
                score += 5; reasons.append({"text": "Confirmed intraday uptrend (HH/HL)", "impact": 5})
            elif indicators.get("trend_direction") == "BEARISH_TREND":
                score -= 5; reasons.append({"text": "Intraday downtrend active (LH/LL)", "impact": -5})
        
        # FIX F7: Remove floor from L1 score to allow negative baseline conviction to drag down L2 boosters
        # OLD: Return max(0, min(40, score)) — neutralized L1 penalties
        # NEW: Return negative L1 score so it deducts from total final_score
        return min(40, score), {"score": score, "reasons": reasons}

    # R4-4 FIX: Removed unused df_15m, df_1h params — L2 only reads from indicators dict.
    # FUTURE: Adding candle pattern analysis (engulfing, hammer at VWAP) from df_15m
    # would significantly improve L2 entry quality detection.
    def _run_layer2(self, indicators, df_15m=None):
        price, ema20, distance_vwap = indicators["price"], indicators["ema20"], indicators["distance_vwap"]
        rvol, structure_ok = indicators.get("rvol", 0), indicators.get("structure_ok", True)
        is_pullback, is_short_pullback = indicators.get("is_pullback", False), indicators.get("is_short_pullback", False)
        # FIX R11: Dead Gate revived. Use correctly populated dictionary key 'is_exhausted'.
        is_exhausted = indicators.get("is_exhausted", False)
        ema_1h_trend_up = indicators["ema_1h_trend_up"]
        score, reasons, alpha_mode = 0, [], "NONE"
        dynamic_zones = {}
        
        # 1. Exhaustion Phase (EXT) Gate
        # [V31 GAP#4 FIX] Don't auto-kill legitimate MOMENTUM trades
        # NEW: If strong volume + structure confirms momentum, give degraded score instead of zero
        if is_exhausted:
            if price > ema20:
                is_strong_momentum = rvol > 2.5 and structure_ok
            else:
                is_strong_momentum = rvol > 2.5 and indicators.get("trend_direction") == "BEARISH_TREND"
            
            # Use absolute distance for mild exhaustion check (ATR normalized)
            atr_pct = indicators.get("atr", 1e-6) / max(price, 1e-6) * 100
            dist_vwap_atr = abs(distance_vwap) / max(atr_pct, 1e-6)
            dist_ema_atr = abs(indicators.get("distance_ema", 999)) / max(atr_pct, 1e-6)
            
            is_mild_exhaustion = dist_vwap_atr < 3.0 and dist_ema_atr < 2.5
            
            if is_strong_momentum and is_mild_exhaustion:
                # Degraded MOMENTUM — reduced score, not zero
                alpha_mode = "MOMENTUM_EXTENDED" if price > ema20 else "SHORT_MOMENTUM_EXTENDED"
                score += 20  # Reduced from 40 (normal MOMENTUM base)
                reasons.append({"text": f"{alpha_mode.replace('_', ' ')} (mild): Strong volume, moderate extension", "impact": 20})
                # Continue to confluence checks below (don't return early)
            else:
                alpha_mode = "EXHAUSTED"
                reasons.append({"text": "Price over-extended (EXT Phase) - High Risk of Mean Reversion", "impact": 0})
                
                # P5 FIX: Check bearish/bullish divergence even for exhausted stocks
                if df_15m is not None:
                    try:
                        rsi_div = ta_intraday.IntradayTechnicalAnalysis.detect_rsi_divergence(df_15m)
                        if price > ema20 and rsi_div.get("type") == "Bearish":
                            reasons.append({"text": "EXHAUSTED + Bearish Divergence (AVOID)", "impact": 0})
                        elif price < ema20 and rsi_div.get("type") == "Bullish":
                            reasons.append({"text": "EXHAUSTED + Bullish Divergence (AVOID)", "impact": 0})
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
                indicators["fvg"] = ta_intraday.IntradayTechnicalAnalysis.detect_fvg(df_15m)
                # [V32 P2] 15m MACD Histogram — fastest momentum confirmation
                indicators["macd_15m"] = ta_intraday.IntradayTechnicalAnalysis.calculate_macd_histogram(df_15m)
            except Exception:
                pass

        distance_vwap_abs = abs(distance_vwap)
        # [V46 FIX#5] ATR-normalized VWAP proximity for EARLY mode
        # OLD: abs(distance_vwap) < 1.2 — flat 1.2% regardless of volatility
        #   → Volatile stocks (2%+ daily range): 1.2% is right ON VWAP, too tight
        #   → Calm stocks (0.5% daily range): 1.2% is massively extended, too loose
        # NEW: Normalize by ATR — adapts to each stock's actual volatility profile
        _atr_l2 = indicators.get("atr", 1e-6)
        is_near_vwap = abs(price - indicators.get("vwap", price)) / max(_atr_l2, 1e-6) < 1.0
        is_trending = price > ema20
        # [V41 FIX] Global pre-9:30 AM flag for opening noise suppression
        is_pre_930 = False
        if df_15m is not None and isinstance(df_15m.index, pd.DatetimeIndex) and len(df_15m) > 0:
            last_ts = df_15m.index[-1]
            # Convert Yahoo's tz-naive UTC timestamps to IST for accurate time checking
            if last_ts.tzinfo is None:
                last_ts = last_ts.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                last_ts = last_ts.tz_convert('Asia/Kolkata')
            
            _h, _m = last_ts.hour, last_ts.minute
            if _h == 9 and _m <= 30: 
                is_pre_930 = True
        
        # 2. Alpha Mode Sequence Gate (Total Target: 60)
        # Sequence Priority: 1. Breakout -> 2. Pullback -> 3. Momentum -> 4. Early Base
        
        # 2A. Breakout Phase (Highest Conviction, must check first so it's not hijacked by 'EARLY')
        if indicators.get("accumulation", {}).get("is_breakout", False):
            bk_ctx = indicators.get("accumulation", {})
            bk_score = bk_ctx.get("breakout_score", 0)
            bk_pts = 45 if bk_score >= 60 else 35
            alpha_mode = "BREAKOUT"; score += bk_pts; reasons.append({"text": f"BREAKOUT: {bk_ctx.get('breakout_intensity', 'Valid')} from tight zone", "impact": bk_pts})
            
            # [V23 FIX #4] BREAKOUT_RETEST: If breakout detected but also pulling back to level,
            # overlay retest confidence — this is THE highest probability intraday setup
            if is_pullback:
                alpha_mode = "BREAKOUT_RETEST"
                score += 5; reasons.append({"text": "RETEST: Pulling back to breakout level (highest probability)", "impact": 5})

        # 2B. Pullback Phase
        elif is_pullback or is_short_pullback:
            # [V32 P1 FIX] Increased from 35 to 40 — pullback is higher conviction than EARLY
            pb_score = 40
            pb_reason = "PULLBACK: EMA retracement + recovery" if is_pullback else "SHORT PULLBACK: EMA retracement + rejection"
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
                        context=pb_context,
                        is_short=is_short_pullback
                    )
                    
                    dynamic_zones["stop_loss"] = pb_engine.get("stop_loss")
                    dynamic_zones["target"] = pb_engine.get("target_2")
                    adv_score = pb_engine.get("entry_score", 0)
                    if adv_score >= 70:
                        pb_score = 45
                        pb_reason = f"{'PULLBACK' if is_pullback else 'SHORT PULLBACK'} (V4.5 Verified) - Quality: {pb_engine.get('entry_quality', 'B')}"
                        if pb_engine.get("signals", {}).get("liquidity_sweep"):
                            score += 10; reasons.append({"text": "Confluence: Stop-Hunt Trap (Liquidity Sweep)", "impact": 10})
                except Exception:
                    pass
            
            # [V20 VANGUARD] Fair Value Gap (+20 pts)
            is_trade_short = is_short_pullback
            pa_score = indicators.get("pa_score", 0)
            fvg = indicators.get("fvg", {})
            if fvg.get("is_tapping"):
                # Must be a bullish FVG for a long, bearish FVG for a short
                is_fvg_aligned = (fvg.get("type") == "Bullish" and not is_trade_short) or (fvg.get("type") == "Bearish" and is_trade_short)
                if pa_score > 60 and is_fvg_aligned: # Validates it's rejecting the FVG in the right direction
                    pb_score += 20
                    pb_reason += " + FVG Defense (SMART MONEY)"
            
            alpha_mode = "PULLBACK" if is_pullback else "SHORT_PULLBACK"; score += min(60, pb_score); reasons.append({"text": pb_reason, "impact": min(60, pb_score)})
            
        # 2C. Momentum Phase
        # [V41 FIX] Block MOMENTUM pre-9:30 AM (it's fake momentum, just 1 candle deep)
        # [AUDIT GAP-A FIX] ATR-distance gate — reject if already extended > 1.5 ATR from EMA20
        # Without this gate, MOMENTUM fires on stocks that have already moved 2-3% from their base.
        # By the time you enter, the move is 60-70% done → poor RR, high mean-reversion risk.
        elif is_trending and distance_vwap >= 1.0 and rvol > 1.5 and not is_pre_930 and (abs(price - ema20) / max(indicators.get("atr", 1e-6), 1e-6)) < 1.5:
            alpha_mode = "MOMENTUM"; score += 40; reasons.append({"text": "MOMENTUM: Strong trend + volume (within 1.5 ATR)", "impact": 40})
        
        # [V23 FIX #15] OPENING DRIVE DETECTION (9:15-9:45) — Moved BEFORE EARLY mode
        # OLD: Only fired when alpha_mode == "NONE", so gap-and-go setups were mislabeled as EARLY
        # NEW: Check during opening window for ANY pre-EARLY state, overlaying the strongest label
        if alpha_mode in ["NONE", "EARLY"] and df_15m is not None and isinstance(df_15m.index, pd.DatetimeIndex):
            try:
                od_h, od_m = df_15m.index[-1].hour, df_15m.index[-1].minute
                is_opening_window = (od_h == 9 and 15 <= od_m <= 45)
                if is_opening_window:
                    orb = indicators.get("orb", {})
                    gap = indicators.get("gap", {})
                    # [V31 GAP#6 FIX] OPENING_DRIVE was DEAD — wrong field names!
                    # OLD: gap.get("gap_percent") → actual key is "pct"
                    # OLD: orb.get("breakout_type") → actual key is "status" with values like "Breakout"
                    is_gap_go = gap.get("pct", 0) > 0.5 and rvol > 2.0
                    is_orb = orb.get("status") in ["Breakout", "Early Breakout"]
                    is_gap_dump = gap.get("pct", 0) < -0.5 and rvol > 2.0
                    is_orb_down = orb.get("status") in ["Breakdown", "Early Breakdown"]
                    
                    if is_gap_go or is_orb:
                        if alpha_mode == "EARLY":
                            alpha_mode = "OPENING_DRIVE"
                            reasons.append({"text": f"OPENING DRIVE: {'Gap-and-Go' if is_gap_go else 'ORB Breakout'} (upgraded from EARLY)", "impact": 0})
                        else:
                            alpha_mode = "OPENING_DRIVE"
                            score += 42; reasons.append({"text": f"OPENING DRIVE: {'Gap-and-Go' if is_gap_go else 'ORB Breakout'}", "impact": 42})
                    elif is_gap_dump or is_orb_down:
                        if alpha_mode == "EARLY":
                            alpha_mode = "SHORT_OPENING_DRIVE"
                            reasons.append({"text": f"SHORT OPENING DRIVE: {'Gap-and-Dump' if is_gap_dump else 'ORB Breakdown'} (upgraded from EARLY)", "impact": 0})
                        else:
                            alpha_mode = "SHORT_OPENING_DRIVE"
                            score += 42; reasons.append({"text": f"SHORT OPENING DRIVE: {'Gap-and-Dump' if is_gap_dump else 'ORB Breakdown'}", "impact": 42})
            except Exception:
                pass

        # 2D. Early Phase Base (Catch-all for standard healthy setups that aren't explosive yet)
        # [V32 P1 FIX] Reduced from 45 to 30 — EARLY is lowest conviction, shouldn't outscore PULLBACK
        # [AUDIT GAP-B FIX] Require RVOL > 1.2 — without at least above-average volume,
        # there's no institutional interest to drive the move. EARLY trades without volume are coin-flips.
        if alpha_mode == "NONE" and is_near_vwap and is_trending and structure_ok and rvol > 1.2:
            alpha_mode = "EARLY"; score += 20; reasons.append({"text": "EARLY: Near VWAP + Trend + Structure + Volume (low conviction)", "impact": 20})
            
        # 2E. SHORT Phase (Bearish setups)
        if alpha_mode == "NONE" and not is_trending and distance_vwap < -1.0 and rvol > 1.5 and not is_pre_930:
            # Market structure must confirm: Lower Highs + Lower Lows
            if indicators.get("trend_direction") == "BEARISH_TREND":
                alpha_mode = "SHORT_MOMENTUM"
                score += 40
                reasons.append({"text": "SHORT: Below VWAP + Bearish structure + Volume", "impact": 40})

        # 2F. SHORT PULLBACK (Mean reversion to VWAP from below)
        elif alpha_mode == "NONE" and not is_trending:
            touched_resistance = price >= ema20 - (indicators.get("atr", 0) * 0.3) if ema20 > price else False
            trend_resuming_down = df_15m['close'].iloc[-1] < df_15m['close'].iloc[-2] if df_15m is not None else False
            if touched_resistance and trend_resuming_down and price < (ema20 + indicators.get("atr", 0) * 0.1):
                pb_score = 35
                pb_reason = "SHORT PULLBACK: VWAP rejection + trend resumption"
                
                if df_15m is not None:
                    try:
                        liq_ctx = liquidity_service.get_liquidity(indicators.get("symbol", ""))
                        vol_mult = 1.25 if liq_ctx.get("level") in ["High", "Moderate"] else 1.0
                        pb_context = {"smart_gate": indicators.get("smart_gate_bypass", False), "vol_mult": vol_mult}
                        
                        pb_engine = ta_intraday.IntradayTechnicalAnalysis.detect_pullback_entry_v45(
                            df_15m, 
                            indicators.get("vwap_val", price),
                            context=pb_context,
                            is_short=True
                        )
                        
                        if pb_engine.get("is_entry"):
                            dynamic_zones["stop_loss"] = pb_engine.get("stop_loss")
                            dynamic_zones["target"] = pb_engine.get("target_2")
                            adv_score = pb_engine.get("entry_score", 0)
                            if adv_score >= 70:
                                pb_score = 45
                                pb_reason = f"SHORT PULLBACK (V4.5 Verified) - Quality: {pb_engine.get('entry_quality', 'B')}"
                                if pb_engine.get("signals", {}).get("liquidity_sweep"):
                                    score += 10; reasons.append({"text": "Confluence: Stop-Hunt Trap (Liquidity Sweep UP)", "impact": 10})
                    except Exception:
                        pass
                
                alpha_mode = "SHORT_PULLBACK"
                score += pb_score
                reasons.append({"text": pb_reason, "impact": pb_score})
            
        # R5-3 FIX: Signal Confluence Boosters
        # These only fire when a valid alpha mode has been detected (EARLY/PULLBACK/MOMENTUM).
        # They CONFIRM the setup quality — they don't create phantom signals.
        # Without confluence, PULLBACK max=50 and MOMENTUM max=45, never reaching 60.
        if alpha_mode != "NONE":
            is_short_alpha = "SHORT" in alpha_mode
            
            # [V40 GAP] Snapshot score before boosters for diminishing returns calculation
            l2_data_base_score = score
            
            # [V43 AUDIT FIX #5] Removed L2 RVOL booster — RVOL already scored in L1 (+10) and L3 (-15)
            # OLD: if rvol > 2.5: score += 10 — caused triple-counting of volume across all 3 layers
            
            if is_short_alpha:
                if not ema_1h_trend_up: score += 5; reasons.append({"text": "Booster: 1H Trend Down", "impact": 5})
            else:
                if ema_1h_trend_up: score += 5; reasons.append({"text": "Booster: 1H Trend Up", "impact": 5})

            mfi = indicators.get("mfi", 50)
            if is_short_alpha:
                if mfi < 30 and rvol > 1.5:
                    score += 7; reasons.append({"text": "Confluence: Bearish Institutional Flow (MFI <30)", "impact": 7})
                elif mfi > 70:
                    score -= 5; reasons.append({"text": "Warning: MFI Overbought (>70, potential squeeze)", "impact": -5})
            else:
                if mfi > 70 and rvol > 1.5:
                    score += 7; reasons.append({"text": "Confluence: Institutional Flow (MFI >70)", "impact": 7})
                elif mfi < 30:
                    score -= 5; reasons.append({"text": "Warning: MFI Oversold (<30, potential reversal)", "impact": -5})

            # 1. RSI Divergence
            rsi_div = indicators.get("rsi_divergence", {})
            if is_short_alpha:
                if rsi_div.get("type") == "Bearish":
                    bonus = 8 if rsi_div.get("severity") == "High" else 5
                    score += bonus; reasons.append({"text": f"Confluence: Bearish RSI Divergence ({rsi_div.get('severity', 'Moderate')})", "impact": bonus})
            else:
                if rsi_div.get("type") == "Bullish":
                    bonus = 8 if rsi_div.get("severity") == "High" else 5
                    score += bonus; reasons.append({"text": f"Confluence: Bullish RSI Divergence ({rsi_div.get('severity', 'Moderate')})", "impact": bonus})
            
            # 2. Squeeze Breakout
            squeeze = indicators.get("squeeze", {})
            if squeeze.get("is_breakout") and squeeze.get("is_squeeze"):
                score += 7; reasons.append({"text": "Confluence: Squeeze Breakout (energy release)", "impact": 7})
            elif squeeze.get("is_squeeze"):
                score += 3; reasons.append({"text": "Confluence: Squeeze Building (coiling energy)", "impact": 3})
            
            # 3. Order Flow Accumulation
            # [AUDIT GAP-C] Use Kite L2 depth (REAL bid/ask) when available, fallback to CVD proxy
            kite_depth = indicators.get("kite_depth")
            if kite_depth:
                # REAL order flow from Kite Level-2 market depth
                depth_imbalance = kite_depth.get("depth_imbalance", "NEUTRAL")
                bid_ask_ratio = kite_depth.get("bid_ask_ratio", 1.0)
                spread_pct = kite_depth.get("spread_pct", 0.0)
                
                if is_short_alpha:
                    if depth_imbalance in ["SELL", "STRONG_SELL"]:
                        bonus = 10 if depth_imbalance == "STRONG_SELL" else 7
                        score += bonus; reasons.append({"text": f"Confluence: Kite L2 Sell Pressure (Bid/Ask {bid_ask_ratio:.1f})", "impact": bonus})
                    elif depth_imbalance in ["BUY", "STRONG_BUY"]:
                        score -= 7; reasons.append({"text": f"Warning: Kite L2 Buy Support (Bid/Ask {bid_ask_ratio:.1f})", "impact": -7})
                else:
                    if depth_imbalance in ["BUY", "STRONG_BUY"]:
                        bonus = 10 if depth_imbalance == "STRONG_BUY" else 7
                        score += bonus; reasons.append({"text": f"Confluence: Kite L2 Buy Pressure (Bid/Ask {bid_ask_ratio:.1f})", "impact": bonus})
                    elif depth_imbalance in ["SELL", "STRONG_SELL"]:
                        score -= 7; reasons.append({"text": f"Warning: Kite L2 Sell Pressure (Bid/Ask {bid_ask_ratio:.1f})", "impact": -7})
                
                # Wide spread penalty — illiquid stocks have wider spreads
                if spread_pct > 0.15:
                    score -= 5; reasons.append({"text": f"Warning: Wide Spread ({spread_pct:.2f}%, execution risk)", "impact": -5})
            else:
                # Fallback: CVD Proxy (close-position-in-range estimate)
                cvd = indicators.get("cvd", {})
                if is_short_alpha:
                    if cvd.get("score", 50) <= 25:
                        score += 3; reasons.append({"text": f"Confluence: Distribution Proxy (CVD {cvd.get('cvd_ratio', 0):+.0%})", "impact": 3})
                else:
                    if cvd.get("score", 50) >= 75:
                        score += 3; reasons.append({"text": f"Confluence: Accumulation Proxy (CVD {cvd.get('cvd_ratio', 0):+.0%})", "impact": 3})
            
            # 4 & 8. Multi-Collinear Momentum Group (EMA Fan + MACD)
            ema_fan = indicators.get("ema_fan", {})
            macd = indicators.get("macd_15m", {})
            
            ema_bonus, macd_bonus, macd_penalty = 0, 0, 0
            ema_reason, macd_reason, macd_warn_reason = "", "", ""

            if is_short_alpha:
                if ema_fan.get("status") == "Bearish Fan":
                    ema_bonus = 5; ema_reason = "Confluence: Bearish EMA Fan (9<20<50<200)"
                
                if macd.get("zero_cross_bearish"):
                    macd_bonus = 8; macd_reason = "Confluence: MACD Zero-Cross Bearish (trend reversal)"
                elif macd.get("histogram_falling"):
                    macd_bonus = 5; macd_reason = "Confluence: 15m MACD Histogram Falling"
                elif macd.get("histogram_rising") and alpha_mode not in ["SHORT_PULLBACK"]:
                    macd_penalty = 5; macd_warn_reason = "Warning: 15m MACD Momentum Rising"
            else:
                if ema_fan.get("status") == "Bullish Fan":
                    ema_bonus = 5; ema_reason = "Confluence: Bullish EMA Fan (9>20>50>200)"
                
                if macd.get("zero_cross_bullish"):
                    macd_bonus = 8; macd_reason = "Confluence: MACD Zero-Cross Bullish (trend reversal)"
                elif macd.get("histogram_rising"):
                    macd_bonus = 5; macd_reason = "Confluence: 15m MACD Histogram Rising"
                elif macd.get("histogram_falling") and alpha_mode not in ["PULLBACK", "BREAKOUT_RETEST"]:
                    macd_penalty = 5; macd_warn_reason = "Warning: 15m MACD Momentum Fading"

            # Apply Max Momentum Bonus to prevent Collinearity Bias
            if ema_bonus > 0 or macd_bonus > 0:
                best_bonus = max(ema_bonus, macd_bonus)
                score += best_bonus
                if best_bonus == macd_bonus and macd_bonus > 0:
                    reasons.append({"text": macd_reason, "impact": macd_bonus})
                elif ema_bonus > 0:
                    reasons.append({"text": ema_reason, "impact": ema_bonus})
                    
            if macd_penalty > 0:
                score -= macd_penalty
                reasons.append({"text": macd_warn_reason, "impact": -macd_penalty})
                
            # 5. Value Area integration
            poc_bounce = indicators.get("poc_bounce", {})
            if is_short_alpha:
                if poc_bounce.get("is_vah_rejection"):
                    score += 15; reasons.append({"text": "Confluence: VAH Rejection (Bearish resistance confirmed)", "impact": 15})
                if poc_bounce.get("is_bounce") or poc_bounce.get("is_val_bounce"):
                    score -= 15; reasons.append({"text": "Warning: V-POC/VAL Bounce (Buying support)", "impact": -15})
            else:
                if poc_bounce.get("is_bounce"):
                    score += 15; reasons.append({"text": "Confluence: V-POC Bounce (Core Volume Defense)", "impact": 15})
                if poc_bounce.get("is_val_bounce"):
                    score += 15; reasons.append({"text": "Confluence: VAL Bounce (Value Area Low Defense)", "impact": 15})
                if poc_bounce.get("is_vah_rejection"):
                    score -= 15; reasons.append({"text": "Warning: VAH Rejection (Bearish volume rejection)", "impact": -15})
                    
            # 6. Micro-Trend
            if df_15m is not None:
                try:
                    micro = ta_intraday.IntradayTechnicalAnalysis.detect_micro_trend(df_15m)
                    if is_short_alpha:
                        if micro.get("lh"):
                            score += 5; reasons.append({"text": "Confluence: Micro Lower-High Structure", "impact": 5})
                        elif micro.get("hh_hl"):
                            score -= 5; reasons.append({"text": "Warning: Micro HH-HL Structure", "impact": -5})
                    else:
                        if micro.get("hh_hl"):
                            score += 5; reasons.append({"text": "Confluence: Micro HH-HL Structure", "impact": 5})
                        elif micro.get("lh"):
                            score -= 5; reasons.append({"text": "Confluence: Lower-High Warning", "impact": -5})
                except Exception:
                    pass
            
            # 7. Wash-and-Rinse
            if df_15m is not None:
                try:
                    wash = ta_intraday.IntradayTechnicalAnalysis.detect_wash_and_rinse(df_15m)
                    if wash.get("is_trap"):
                        trap_type = wash.get("trap_type", "Bullish")
                        if trap_type == "Bullish" and not is_short_alpha:
                            bonus = 10 if wash.get("strength") == "High" else 7
                            score += bonus; reasons.append({"text": f"Confluence: Stop-Hunt Reversal ({wash.get('level', 'Key Level')})", "impact": bonus})
                        elif trap_type == "Bearish" and is_short_alpha:
                            bonus = 10 if wash.get("strength") == "High" else 7
                            score += bonus; reasons.append({"text": f"Confluence: Bearish Stop-Hunt Reversal ({wash.get('level', 'Key Level')})", "impact": bonus})
                except Exception:
                    pass
            
            # 8. MACD (Moved to combined Momentum Group above to fix multi-collinearity)
            
            # 9. VWAP Breakdown/Reclaim
            if is_short_alpha:
                if indicators.get("vwap_breakdown") and rvol > 1.5:
                    score += 10; reasons.append({"text": "Confluence: VWAP Breakdown (institutional sell confirmation)", "impact": 10})
            else:
                if indicators.get("vwap_reclaim") and rvol > 1.5:
                    score += 10; reasons.append({"text": "Confluence: VWAP Reclaim (institutional buy confirmation)", "impact": 10})

            # 10. Candle Pattern
            if df_15m is not None and len(df_15m) >= 3:
                last = df_15m.iloc[-1]
                prev = df_15m.iloc[-2]
                c_range = float(last['high']) - float(last['low'])
                body = abs(float(last['close']) - float(last['open']))
                lower_wick = min(float(last['close']), float(last['open'])) - float(last['low'])
                upper_wick = float(last['high']) - max(float(last['close']), float(last['open']))
                
                vwap_val = indicators.get("vwap_val", 0)
                atr = indicators.get("atr", max(c_range, 1e-6))
                ema20 = indicators.get("ema20", 0)
                
                if is_short_alpha:
                    is_shooting_star = (upper_wick > body * 2) and (float(last['close']) < float(last['open'])) and c_range > 0
                    near_res = (abs(float(last['high']) - vwap_val) < atr * 0.3) or (abs(float(last['high']) - ema20) < atr * 0.3)
                    if is_shooting_star and near_res:
                        score += 8; reasons.append({"text": "Confluence: Bearish Shooting Star at Resistance", "impact": 8})
                    
                    is_bear_engulfing = (
                        float(prev['close']) > float(prev['open']) and   # prev bullish
                        float(last['close']) < float(last['open']) and   # curr bearish
                        float(last['close']) < float(prev['open']) and   # body engulfs down
                        float(last['open']) > float(prev['close'])
                    )
                    if is_bear_engulfing and rvol > 1.2:
                        score += 7; reasons.append({"text": "Confluence: Bearish Engulfing (reversal)", "impact": 7})
                else:
                    is_hammer = (lower_wick > body * 2) and (float(last['close']) > float(last['open'])) and c_range > 0
                    near_support = (abs(float(last['low']) - vwap_val) < atr * 0.3) or (abs(float(last['low']) - ema20) < atr * 0.3)
                    if is_hammer and near_support:
                        score += 8; reasons.append({"text": "Confluence: Bullish Hammer at Support", "impact": 8})
                    
                    is_engulfing = (
                        float(prev['close']) < float(prev['open']) and   # prev bearish
                        float(last['close']) > float(last['open']) and   # curr bullish
                        float(last['close']) > float(prev['open']) and   # body engulfs
                        float(last['open']) < float(prev['close'])
                    )
                    if is_engulfing and rvol > 1.2:
                        score += 7; reasons.append({"text": "Confluence: Bullish Engulfing (reversal)", "impact": 7})
                
        # P17: Smart Gate Reversal Booster
        # If the stock bypassed the DNA block via conviction signals, inject 15 points
        # to counteract the L1 penalties safely.
        if indicators.get("smart_gate_bypass", False):
            score += 15; reasons.append({"text": "Confluence: Conviction Reversal (Smart Gate Bypass)", "impact": 15})
        
        # [V40 GAP#7 FIX] Confluence Booster Diminishing Returns
        # Problem: 10+ weak signals stack additively to create false 85+ conviction scores.
        # Fix: Apply retroactive decay curve on total booster contribution.
        # First 25 pts: 100% (genuine strong confluences like VPOC bounce, RSI div)
        # Next 15 pts (25-40): 60% (moderate confluences contribute less)
        # Above 40 pts: 30% (marginal signals severely discounted)
        # Example: Raw boost 55 → 25 + (15×0.6) + (15×0.3) = 25 + 9 + 4.5 = 38.5
        _base_mode_score = l2_data_base_score if 'l2_data_base_score' in locals() else 0
        _total_boost = score - _base_mode_score  # Isolate booster contribution
        if _total_boost > 25:
            _tier1 = 25  # Full value
            _tier2 = min(_total_boost - 25, 15) * 0.6
            _tier3 = max(_total_boost - 40, 0) * 0.3
            _decayed_boost = int(_tier1 + _tier2 + _tier3)
            _clipped = _total_boost - _decayed_boost
            if _clipped > 0:
                score = _base_mode_score + _decayed_boost
                reasons.append({"text": f"Diminishing Returns: Booster overflow clipped by {_clipped} pts", "impact": -_clipped})
        
        # [V42] Daily Squeeze Release Booster
        # Multi-day consolidation breakout + intraday momentum confirmation = explosive 5%+ runners
        daily_bo = indicators.get("daily_breakout", {})
        if daily_bo.get("is_consolidation_breakout") and alpha_mode in ["BREAKOUT", "MOMENTUM", "OPENING_DRIVE", "BREAKOUT_RETEST"]:
            score += 10
            reasons.append({
                "text": f"EXPLOSIVE: {daily_bo.get('range_pct', 0)}% Daily Squeeze Breakout (multi-day compression release)",
                "impact": 10
            })
        
        # FIX C4 & V14.6: Hard Alpha Lock - Guard against phantom conviction from booster-only scores
        if alpha_mode == "NONE":
            # Boosters alone are not enough — no directional edge identified
            return 0, {"score": 0, "mode": "NONE", "reasons": [{"text": "No Alpha Mode: No directional edge (EARLY/PULLBACK/MOMENTUM) detected", "impact": 0}], "dynamic_zones": {}}

        # [V31 GAP#3 FIX] Non-destructive L2 capping
        # OLD: reasons[0]["impact"] -= diff — corrupted the first reason's display value,
        #      making e.g. "PULLBACK: EMA retracement" show negative impact in the UI
        # NEW: Log the overflow transparently without mutating existing reasons
        final_l2 = min(60, score)
        if score > 60:
            reasons.append({"text": f"L2 Capped (raw {score} → {final_l2})", "impact": 0})

        return final_l2, {"score": final_l2, "mode": alpha_mode, "reasons": reasons, "dynamic_zones": dynamic_zones}

    def _run_layer3(self, indicators, df_15m, market_ctx, l2_data=None, liq=None):
        price, ema20, rvol, atr = indicators["price"], indicators["ema20"], indicators["rvol"], indicators["atr"]
        penalty, reasons = 0, []
        alpha_mode = l2_data.get("mode", l2_data.get("alpha_mode", "NONE")) if l2_data else "NONE"
        
        # [GAP #4 FIX] Macro Tape Contradiction
        day_change_pct = market_ctx.get("day_change_pct", 0.0) if market_ctx else 0.0
        is_trade_short = "SHORT" in alpha_mode
        if is_trade_short and day_change_pct > 0.75:
            penalty += 25
            reasons.append({"text": f"Penalty: Tape Contradiction (Shorting a +{day_change_pct}% bull tape)", "impact": -25})
        elif not is_trade_short and day_change_pct < -0.75:
            penalty += 25
            reasons.append({"text": f"Penalty: Tape Contradiction (Longing a {day_change_pct}% bear tape)", "impact": -25})
            
        # V14.1 FIX: Smart L3 EMA Penalty (Synced with Step 1 Smart Gate)
        # [V43 AUDIT FIX #4] Only penalize Longs below EMA20 — Shorts WANT to be below EMA20
        is_below_ema = price < ema20
        has_conviction = indicators.get("smart_gate_bypass", False)
        # [V46 FIX#1] Exempt PULLBACK from strict EMA penalty
        # The engine explicitly allows pullback entries up to 0.1 ATR below EMA20 (L1034).
        # Penalizing them here with -25 contradicts that tolerance and kills the best entries.
        if is_below_ema and not has_conviction and not is_trade_short and alpha_mode != "PULLBACK":
            penalty += 25; reasons.append({"text": "Penalty: Below EMA20 (no conviction reclaim)", "impact": -25})
        elif is_below_ema and has_conviction and not is_trade_short:
            penalty += 10; reasons.append({"text": "Caution: Below EMA20 (smart gate recovery in progress)", "impact": -10})
        
        distance_ema_atr = abs(price - ema20) / max(atr, 1e-6)
        
        # [PHASE 1 FIX] Normalize Chop Distance to ATR instead of arbitrary 0.5%
        # Tightened chop threshold to 0.25 ATR to adapt to stock volatility
        if distance_ema_atr < 0.25 and alpha_mode != "PULLBACK" and rvol < 0.8: 
            penalty += 10; reasons.append({"text": "Penalty: Too close to EMA on dead volume (chop risk)", "impact": -10})
        
        if rvol < 0.8: 
            penalty += 15; reasons.append({"text": "Penalty: Low RVOL (no institutional volume)", "impact": -15})
        
        # [V32 P3 FIX] VWAP Oscillation Penalty — stocks chopping across VWAP are untradeable
        # analyze_vwap_advanced() detects 3+ crosses in last 10 candles = chop zone
        if indicators.get("vwap_oscillating", False) and alpha_mode not in ["BREAKOUT", "OPENING_DRIVE", "SHORT_BREAKOUT", "SHORT_OPENING_DRIVE"]:
            penalty += 15; reasons.append({"text": "Penalty: VWAP Oscillation (chop zone, 3+ crosses)", "impact": -15})
        
        # [V36 GAP#1+2 FIX] VWAP Chase Penalty — moved inside L3 from post-L3 block
        # OLD: Applied after L3 cap, bypassing MAX_L3_PENALTY protection
        # NEW: Inside L3, subject to cap. Exempts MOMENTUM/BREAKOUT/OPENING_DRIVE
        #      because their alpha IS distance from VWAP — penalizing extension is circular
        # [PHASE 1 FIX] Absolute VWAP Extension Guard
        # Exempts MOMENTUM/BREAKOUT/OPENING_DRIVE from minor chase, but absolutely penalizes > 3.0 ATR extension
        vwap_chase_dist = abs(price - indicators.get("vwap_val", price)) / max(atr, 1e-6)
        # [V46 FIX#4] Added PULLBACK and SHORT_PULLBACK to exemption list
        # Pullbacks target EMA retracement, NOT VWAP proximity. A trending stock that
        # pulls back perfectly to EMA20 but is 1.6 ATR above VWAP was being penalized -10,
        # killing the highest-probability trend-following entries.
        is_exempt_alpha = alpha_mode in ["MOMENTUM", "MOMENTUM_EXTENDED", "BREAKOUT", "BREAKOUT_RETEST", "OPENING_DRIVE", "PULLBACK", "SHORT_PULLBACK", "SHORT_MOMENTUM", "SHORT_MOMENTUM_EXTENDED", "SHORT_BREAKOUT", "SHORT_OPENING_DRIVE"]
        
        if not is_exempt_alpha or vwap_chase_dist > 3.0:
            if vwap_chase_dist > 1.5:
                chase_pen = 25 if vwap_chase_dist > 3.0 else (15 if vwap_chase_dist > 2.5 else 10)
                penalty += chase_pen; reasons.append({"text": f"Penalty: VWAP Chase ({vwap_chase_dist:.1f} ATR away)", "impact": -chase_pen})
            
        # [V24 V4-FIX 2] Volume Climax / Absorption Trap
        # High volume on a tiny candlestick body signifies institutional resistance, not momentum
        last_candle_body = abs(df_15m.iloc[-1]['close'] - df_15m.iloc[-1]['open'])
        last_candle_range = max(df_15m.iloc[-1]['high'] - df_15m.iloc[-1]['low'], 0.01)
        is_doji = (last_candle_body / last_candle_range) < 0.25
        if rvol > 3.0 and is_doji:
            penalty += 30; reasons.append({"text": "Penalty: Volume Climax Absorption (Extreme Volume Doji Trap)", "impact": -30})
        
        # [V12.9] Liquidity Constraint
        if not liq:
            liq = liquidity_service.get_liquidity(indicators.get("symbol", ""))
            
        adv20 = liq.get("adv20", 0)
        daily_turnover = adv20 * price
        # FIX C3: Align threshold with Fix #4 turnover bands
        # OLD: threshold was ₹5Cr (50M) — inconsistent with new 'Very Low' = <₹1Cr
        # NEW: penalty at < ₹2Cr, which is the institutional minimum for safe intraday participation
        if daily_turnover < 20_000_000 and adv20 > 0:  # ₹2 Crore minimum
            penalty += 100; reasons.append({"text": "HARD REJECT: Insufficient institutional liquidity (< ₹2 Cr)", "impact": -100})
        # R4-9 FIX: Unknown liquidity (adv20 == 0) should get FULL penalty, not a pass
        elif adv20 == 0:
            penalty += 20; reasons.append({"text": "Penalty: Unknown Liquidity (no ADV20 data)", "impact": -20})
        
        last_candle = df_15m.iloc[-1]; high, low, close = last_candle['high'], last_candle['low'], last_candle['close']
        candle_range = high - low
        # [PHASE 1 FIX] Volume-Confirmed Rejections
        # A wick is only institutional rejection if volume is high. Otherwise, it's just low-liquidity noise.
        try:
            vol_ma = df_15m['volume'].rolling(20).mean().iloc[-1]
            curr_vol = df_15m['volume'].iloc[-1]
            is_high_volume_wick = curr_vol > vol_ma
        except:
            is_high_volume_wick = True  # Fail-safe
            
        # P8 FIX: Only penalize upper wick on BEARISH candles (close < open)
        if candle_range > 0 and (high - close) / candle_range > 0.5 and close < last_candle['open'] and is_high_volume_wick and not is_trade_short:
            penalty += 15; reasons.append({"text": "Penalty: Bearish upper wick (high volume selling pressure)", "impact": -15})
        elif candle_range > 0 and (close - low) / candle_range > 0.5 and close > last_candle['open'] and is_high_volume_wick and is_trade_short:
            penalty += 15; reasons.append({"text": "Penalty: Bullish lower wick vs Short (high volume buying support)", "impact": -15})
            
        # [V23 FIX #12] RR Gate Revival — use actual L2 dynamic zones when available
        # OLD: rr_ratio = (atr * reward_mult) / (atr * 1.5) = CONSTANT 1.33 or 2.0 — gate NEVER fired
        # NEW: Use L2's target/stop_loss for real trade-level RR assessment
        dynamic_target = l2_data.get("dynamic_zones", {}).get("target") if l2_data else None
        dynamic_sl = l2_data.get("dynamic_zones", {}).get("stop_loss") if l2_data else None
        
        if is_trade_short:
            if dynamic_target and dynamic_sl and dynamic_sl > price and dynamic_target < price:
                actual_reward = price - dynamic_target
                actual_risk = dynamic_sl - price
                rr_ratio = actual_reward / max(actual_risk, 1e-6)
            else:
                actual_sl_distance = max(atr * (2.0 if indicators.get("india_vix", 15) > 20 else 1.5), price * 0.005)
                pivot_vals = [v for v in indicators.get("pivots", {}).values() if isinstance(v, (int, float)) and v < price * 0.998]
                if pivot_vals:
                    nearest_reward = price - max(pivot_vals)
                    rr_ratio = nearest_reward / max(actual_sl_distance, 1e-6)
                else:
                    rr_ratio = 1.5
        else:
            if dynamic_target and dynamic_sl and dynamic_sl < price and dynamic_target > price:
                actual_reward = dynamic_target - price
                actual_risk = price - dynamic_sl
                rr_ratio = actual_reward / max(actual_risk, 1e-6)
            else:
                # [PHASE 1 FIX] Prevent artificial RR penalties on unmapped charts.
                # If we don't have dynamic L2 zones and no clear pivots, assume a momentum-based trailing target 
                # rather than hardcoding a failing RR ratio that triggers the penalty.
                actual_sl_distance = max(atr * (2.0 if indicators.get("india_vix", 15) > 20 else 1.5), price * 0.005)
                pivot_vals = [v for v in indicators.get("pivots", {}).values() if isinstance(v, (int, float)) and v > price * 1.002]
                if pivot_vals:
                    nearest_reward = min(pivot_vals) - price
                    rr_ratio = nearest_reward / max(actual_sl_distance, 1e-6)
                else:
                    rr_ratio = 1.5  # Assumed viable RR for momentum run
        
        if rr_ratio < 1.2: 
            penalty += 15; reasons.append({"text": f"Penalty: Poor Risk/Reward ({rr_ratio:.1f})", "impact": -15})
        
        # [V31 GAP#12 FIX] Liquidity Trap Detection — detect_liquidity_trap() was fully
        # implemented in ta_intraday.py but NEVER called from engine
        try:
            trap = ta_intraday.IntradayTechnicalAnalysis.detect_liquidity_trap(df_15m)
            if trap.get("trap_move_detected"):
                penalty += 20; reasons.append({"text": "Penalty: Liquidity Trap Detected (Distribution)", "impact": -20})
        except Exception:
            pass
        
        # V15 Pioneer Fix: Time Decay Matrix
        # [V43 AUDIT FIX #6] Convert Yahoo UTC timestamps to IST before time checks
        try:
            if df_15m is not None and not df_15m.empty:
                current_time = df_15m.index[-1]
                # Convert to IST — Yahoo returns UTC timestamps
                if hasattr(current_time, 'tzinfo') and current_time.tzinfo is None:
                    current_time = current_time.tz_localize('UTC').tz_convert('Asia/Kolkata')
                elif hasattr(current_time, 'tz_convert'):
                    current_time = current_time.tz_convert('Asia/Kolkata')
                if hasattr(current_time, 'hour'):
                    h, m = current_time.hour, current_time.minute
                    
                    # V16.1: LOTTO PASS [Hardened]
                    # If the score is exceptional (A+ quality) or volume is parabolic, we reduce time-decay 
                    # to allow high-conviction 'Hero' trades during typical dead zones.
                    is_lotto = (l2_data.get("score", 0) >= 100) or (rvol > 4.0)
                    t_mult = 0.5 if is_lotto else 1.0
                    
                    # Lunch Chop Filter (11:30 to 13:30)
                    if (h == 11 and m >= 30) or h == 12 or (h == 13 and m <= 30):
                        p_val = int(10 * t_mult)
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

        # [V34 GAP#4 FIX] Global Market Regime Integration
        if market_ctx:
            market_trend = market_ctx.get("market_trend", "BULLISH")
            regime_strength = market_ctx.get("regime_strength", "NORMAL")
            is_trade_short = "SHORT" in alpha_mode
            
            # Strong bearish: Nifty trending down with confirmed ADX strength
            # Only penalize when Nifty is clearly bearish (> 0.3% down), with scaled severity
            day_chg = abs(market_ctx.get("day_change_pct", 0.0))
            if market_trend == "BEARISH" and regime_strength in ["STRONG_TREND", "WEAK_TREND"]:
                if not is_trade_short:
                    # Scale penalty: -10 for mild dip (0.3-0.75%), -20 for strong sell-off (>0.75%)
                    pen_val = 20 if day_chg > 0.75 else 10
                    penalty += pen_val; reasons.append({"text": f"Penalty: Market Weakness (Nifty {market_ctx.get('day_change_pct', 0):.2f}%)", "impact": -pen_val})
            elif market_trend == "BULLISH" and regime_strength in ["STRONG_TREND", "WEAK_TREND"]:
                if is_trade_short:
                    pen_val = 20 if day_chg > 0.75 else 10
                    penalty += pen_val; reasons.append({"text": f"Penalty: Broad Market Strength (Nifty +{day_chg:.2f}%) vs Short", "impact": -pen_val})
            
            # Choppy market with no institutional volume = fade everything (Longs & Shorts)
            elif regime_strength == "CHOP" and rvol < 2.0:
                penalty += 10; reasons.append({"text": "Penalty: Choppy Market (Low ADX + Low RVOL)", "impact": -10})
                
            # [V21.3 FIX] Advance/Decline Ratio Penalty
            # Covers the 98% of stocks that lack explicit Sector mapping.
            ad_ratio = market_ctx.get("ad_ratio", 1.0)
            if ad_ratio < 0.4:
                if not is_trade_short:
                    pen = 15 if ad_ratio < 0.2 else 10
                    penalty += pen; reasons.append({"text": f"Penalty: Broad Market Weakness (A/D {ad_ratio:.2f})", "impact": -pen})
        
        # Safe Momentum Check (Requires at least 4 candles)
        # [V43 AUDIT FIX #8] Only penalize Longs for stale highs — for Shorts, declining highs = confirmation
        if len(df_15m) >= 4:
            recent_highs, prev_high = df_15m['high'].iloc[-3:], df_15m['high'].iloc[-4]
            recent_lows, prev_low = df_15m['low'].iloc[-3:], df_15m['low'].iloc[-4]
            if not is_trade_short and recent_highs.max() <= prev_high: 
                penalty += 5; reasons.append({"text": "Penalty: No momentum (stale move)", "impact": -5})
            elif is_trade_short and recent_lows.min() >= prev_low:
                penalty += 5; reasons.append({"text": "Penalty: No downside momentum (stale lows)", "impact": -5})

        # V16 AUDIT FIX 4: Daily (1D) Macro Trend Penalty
        # [V43 AUDIT FIX #9] Now symmetric: Longs penalized below 1D EMA, Shorts penalized above 1D EMA
        is_1d_bullish = indicators.get("is_1d_bullish", None)
        if not is_trade_short:
            if is_1d_bullish is False and alpha_mode in ["BREAKOUT", "PULLBACK", "EARLY", "MOMENTUM"]:
                penalty += 15; reasons.append({"text": "Penalty: Below Daily 20-EMA (Counter-Trend Risk)", "impact": -15})
            elif is_1d_bullish is None and alpha_mode in ["BREAKOUT", "PULLBACK", "EARLY", "MOMENTUM"]:
                penalty += 5; reasons.append({"text": "Caution: No Daily Data (1D trend unknown)", "impact": -5})
        else:
            if is_1d_bullish is True and alpha_mode in ["SHORT_MOMENTUM", "SHORT_PULLBACK", "SHORT_OPENING_DRIVE"]:
                penalty += 15; reasons.append({"text": "Penalty: Above Daily 20-EMA (Counter-Trend Short)", "impact": -15})
            elif is_1d_bullish is None and alpha_mode in ["SHORT_MOMENTUM", "SHORT_PULLBACK", "SHORT_OPENING_DRIVE"]:
                penalty += 5; reasons.append({"text": "Caution: No Daily Data (1D trend unknown)", "impact": -5})

        # [V45 FIX] Intraday Macro Trend Contradiction (Strict Safeguard)
        # Prevents getting trapped in dead-cat bounces or lower-highs during intraday downtrends
        mkt_struct = indicators.get("market_structure", "NEUTRAL_STRUCTURE")
        if not is_trade_short:
            if mkt_struct == "BEARISH_STRUCTURE":
                penalty += 25; reasons.append({"text": "Penalty: Counter-Trend Long (Intraday LH/LL Structure)", "impact": -25})
        else:
            if mkt_struct == "BULLISH_STRUCTURE":
                penalty += 25; reasons.append({"text": "Penalty: Counter-Trend Short (Intraday HH/HL Structure)", "impact": -25})
            
        # [V24 V3-FIX 3] 1H MACD Momentum Bearish Penalty
        # [V43 AUDIT FIX #10] Only penalize Longs for bearish 1H MACD — for Shorts it's confirmation
        is_1h_mom = indicators.get("is_1h_momentum_bullish", None)
        if not is_trade_short:
            if is_1h_mom is False:
                penalty += 10; reasons.append({"text": "Penalty: 1H MACD Momentum Bearish", "impact": -10})
            elif is_1h_mom is None:
                penalty += 5; reasons.append({"text": "Caution: No 1H Data (momentum unknown)", "impact": -5})
        else:
            if is_1h_mom is True:
                penalty += 10; reasons.append({"text": "Penalty: 1H MACD Momentum Bullish (counter-trend short)", "impact": -10})
            elif is_1h_mom is None:
                penalty += 5; reasons.append({"text": "Caution: No 1H Data (momentum unknown)", "impact": -5})
        
        # P1/P10 FIX: Penalize Bearish RSI Divergence (reversal risk)
        # [V35 GAP#4 FIX] Increased High severity from -10 to -20
        # Bearish div at overbought is one of the strongest reversal signals — was weaker than lunch chop (-20)
        # [V43 AUDIT FIX #1] Only penalize Longs for Bearish RSI Div — for Shorts it's a booster (already in L2)
        rsi_div = indicators.get("rsi_divergence", {})
        if rsi_div.get("type") == "Bearish" and not is_trade_short:
            p_val = 20 if rsi_div.get("severity") == "High" else 10
            penalty += p_val; reasons.append({"text": f"Penalty: Bearish RSI Divergence ({rsi_div.get('severity', 'Moderate')})", "impact": -p_val})
        elif rsi_div.get("type") == "Bullish" and is_trade_short:
            p_val = 20 if rsi_div.get("severity") == "High" else 10
            penalty += p_val; reasons.append({"text": f"Penalty: Bullish RSI Divergence vs Short ({rsi_div.get('severity', 'Moderate')})", "impact": -p_val})
        
        # [V35 GAP#3 FIX] Order Flow Contradiction Penalty
        # [AUDIT GAP-C] Use Kite L2 depth (REAL order flow) when available, fallback to CVD proxy
        kite_depth = indicators.get("kite_depth")
        if kite_depth:
            depth_imbalance = kite_depth.get("depth_imbalance", "NEUTRAL")
            bid_ask_ratio = kite_depth.get("bid_ask_ratio", 1.0)
            # Penalize when real order flow contradicts trade direction
            if not is_trade_short and depth_imbalance in ["SELL", "STRONG_SELL"]:
                pen = 15 if depth_imbalance == "STRONG_SELL" else 10
                penalty += pen; reasons.append({"text": f"Penalty: Kite L2 Sell Pressure vs Long (Bid/Ask {bid_ask_ratio:.1f})", "impact": -pen})
            elif is_trade_short and depth_imbalance in ["BUY", "STRONG_BUY"]:
                pen = 15 if depth_imbalance == "STRONG_BUY" else 10
                penalty += pen; reasons.append({"text": f"Penalty: Kite L2 Buy Support vs Short (Bid/Ask {bid_ask_ratio:.1f})", "impact": -pen})
        else:
            # Fallback: CVD Proxy penalty
            cvd = indicators.get("cvd", {})
            # [V43 AUDIT FIX #2] Only penalize Longs for distribution — for Shorts, distribution is confirmation
            if cvd.get("score", 50) <= 25 and not is_trade_short:
                penalty += 10; reasons.append({"text": "Penalty: Smart Money Distribution (CVD net selling)", "impact": -10})
            elif cvd.get("score", 50) >= 75 and is_trade_short:
                penalty += 10; reasons.append({"text": "Penalty: Smart Money Accumulation vs Short (CVD net buying)", "impact": -10})
        
        # P12 FIX: Penalize Bearish EMA Fan (textbook downtrend structure)
        ema_fan = indicators.get("ema_fan", {})
        # [V43 AUDIT FIX #3] Only penalize Longs for Bearish Fan — for Shorts it's confirmation
        if ema_fan.get("status") == "Bearish Fan" and not is_trade_short:
            penalty += 15; reasons.append({"text": "Penalty: Bearish EMA Fan (9<20<50<200)", "impact": -15})
        elif ema_fan.get("status") == "Bullish Fan" and is_trade_short:
            penalty += 15; reasons.append({"text": "Penalty: Bullish EMA Fan vs Short (9>20>50>200)", "impact": -15})
            
        # PIONEER FIX: Volume Climax / Exhaustion Penalty
        # If the technical footprint shows massive spread over-extension + 5x relative volume, it's a trap.
        exhaust_status = indicators.get("exhaustion", {})
        if exhaust_status.get("is_exhausted") and not is_trade_short:
            # Strongest penalty: it represents buying the very top
            penalty += 20
            # Retrieve exact reason (whether ADR limit, ATR stretch or Volume Climax)
            ex_reasons = exhaust_status.get("reasons", ["System Error"])
            reasons.append({"text": f"Warning: {', '.join(ex_reasons)}", "impact": -20})
        elif is_trade_short:
            # Downside exhaustion check for shorts
            day_open = df_15m['open'].iloc[0] if (df_15m is not None and not df_15m.empty) else price
            atr = indicators.get("atr", 1e-6)
            is_vol_climax_down = (rvol > 5.0) and ((df_15m['high'].iloc[-1] - df_15m['low'].iloc[-1]) > (atr * 2.5)) if (df_15m is not None and not df_15m.empty) else False
            is_short_exhausted = (price < day_open - (atr * 3.0)) or is_vol_climax_down
            if is_short_exhausted:
                penalty += 20
                reasons.append({"text": f"Warning: Downside Exhaustion / Volume Climax", "impact": -20})
        
        # P9 FIX: Time-of-day awareness — opening noise filtering
        # V16 AUDIT FIX 2: Removed duplicate lunch penalty (was stacking -25 with V15 Time Decay at L637)
        # [V23 FIX #7] Don't double-penalty stocks in OPENING_DRIVE mode
        # PIONEER FIX: Intelligent Early Bypass (If Undisputed A+ setup, skip noise penalty)
        if isinstance(df_15m.index, pd.DatetimeIndex) and len(df_15m.index) > 0:
            last_ts = df_15m.index[-1]
            if last_ts.tzinfo is None:
                last_ts = last_ts.tz_localize('UTC').tz_convert('Asia/Kolkata')
            else:
                last_ts = last_ts.tz_convert('Asia/Kolkata')
            
            _h, _m = last_ts.hour, last_ts.minute
            is_pre_930_local = (_h == 9 and _m <= 30)
            
            if is_pre_930_local and alpha_mode not in ["OPENING_DRIVE", "SHORT_OPENING_DRIVE"]:  # Before 9:30 AM IST
                # Check for "Undisputed Execution" bypass: Strong MAs, VWAP control, and high volume
                # [FIX] Lowered thresholds to unlock realistic Morning Alpha
                # [V45] Institutional Gap-and-Go Override: Bypass unconditionally if RVOL > 2.5
                # [V46 FIX#3] Replaced dead ema_score/vwap_score variables with living indicators
                # OLD: ema_score and vwap_score were NEVER populated → always 0 → bypass NEVER fired
                # NEW: pa_score >= 80 (close in top 20% of candle = aggressive buying) + above VWAP
                dist_vwap = indicators.get("distance_vwap", 0)
                is_undisputed = (indicators.get("pa_score", 0) >= 80 and ((dist_vwap > 0 and not is_trade_short) or (dist_vwap < 0 and is_trade_short)) and rvol > 1.5) or rvol > 2.5
                if not is_undisputed:
                    # [V41 FIX] Scale penalty to -20 for aggressive modes trying to bypass OPENING_DRIVE checks
                    pen_val = 20 if alpha_mode in ["BREAKOUT", "BREAKOUT_RETEST", "SHORT_BREAKOUT", "MOMENTUM", "SHORT_MOMENTUM"] else 10
                    penalty += pen_val; reasons.append({"text": f"Penalty: Opening volatility (pre-9:30 noise)", "impact": -pen_val})
                else:
                    reasons.append({"text": "System Guard: Bypassed 9:30 Guard due to A+ Volume & Structure", "impact": 0})
            
            # [V42] 10:15 AM Opening Extension Trap Guard
            # Between 9:30 and 10:15, MOMENTUM/BREAKOUT stocks already far from VWAP
            # are likely opening spikes that will fade. Don't chase them.
            if not is_pre_930_local:
                try:
                    ist_now_l3 = datetime.now(pytz.timezone('Asia/Kolkata'))
                    is_pre_1015 = ist_now_l3.hour == 9 or (ist_now_l3.hour == 10 and ist_now_l3.minute < 15)
                    if is_pre_1015 and alpha_mode in ["MOMENTUM", "BREAKOUT", "OPENING_DRIVE", "MOMENTUM_EXTENDED", "SHORT_MOMENTUM", "SHORT_BREAKOUT", "SHORT_OPENING_DRIVE", "SHORT_MOMENTUM_EXTENDED"]:
                        vwap_val_l3 = indicators.get("vwap_val", price)
                        extension_atr = abs(price - vwap_val_l3) / max(atr, 1e-6)
                        if extension_atr > 2.0:
                            # [V45] Gap-and-Go Override: If it's over-extended but has massive institutional volume (RVOL > 2.5), bypass penalty
                            if rvol > 2.5:
                                reasons.append({
                                    "text": f"Alpha: Bypassed Opening Extension Trap ({extension_atr:.1f} ATR) due to Massive Volume (RVOL {rvol:.1f})",
                                    "impact": 0
                                })
                            else:
                                pen = 15
                                penalty += pen
                                reasons.append({
                                    "text": f"Penalty: Opening Extension Trap ({extension_atr:.1f} ATR from VWAP, wait for 10:15)",
                                    "impact": -pen
                                })
                except Exception:
                    pass
        
        # [V31 GAP#9 FIX] Scale L3 cap by alpha quality
        # F6 FIX: Scale L3 cap by PROPORTIONAL alpha quality to stop protecting garbage
        l1_l2_combined = l2_data.get("score", 0) + (indicators.get("l1_score", 0) if "l1_score" in indicators else 20)
        
        # [V40 GAP#3 FIX] Tiered L3 cap — weak setups get less protection from penalties
        # <40 combined: 90% cap (almost no protection — garbage must die)
        # 40-64: 70% cap (moderate protection)
        # 65+: 55% cap (strong setups retain conviction)
        if l1_l2_combined < 40:
            MAX_L3_PENALTY = max(40, int(l1_l2_combined * 0.9))
        elif l1_l2_combined < 65:
            MAX_L3_PENALTY = max(35, int(l1_l2_combined * 0.7))
        else:
            MAX_L3_PENALTY = max(30, int(l1_l2_combined * 0.55))
        
        has_hard_reject = any("HARD REJECT" in r.get("text", "") for r in reasons)
        if penalty > MAX_L3_PENALTY and not has_hard_reject:
            penalty = MAX_L3_PENALTY
            reasons.append({"text": f"System: L3 Penalty Capped at Maximum (-{MAX_L3_PENALTY} max)", "impact": 0})
        elif has_hard_reject and penalty > MAX_L3_PENALTY:
            reasons.append({"text": f"System: L3 Penalty Cap Bypassed (Hard Reject Active)", "impact": 0})
        
        return penalty, {"penalty": penalty, "reasons": reasons}

    def _get_signal(self, score, alpha_mode="NONE"):
        # [V33 GAP#2 FIX] Aligned thresholds with CONFIG["score_floor"] = 65
        # OLD: BUY at 60 but floor at 65 → 60-64 labeled BUY but excluded from output
        is_short = "SHORT" in alpha_mode
        if score >= 85: return "SELL_STRONG" if is_short else "BUY_STRONG"
        elif score >= 65: return "SELL_SHORT" if is_short else "BUY"
        elif score >= 50: return "NEUTRAL"
        else: return "IGNORE"

    async def evaluate_exit(self, sym: str, entry_price: float, stop_loss: float,
                            target: float, df_15m: pd.DataFrame, entry_time: datetime = None, is_short: bool = False) -> dict:
        """[V23 FIX #10] Exit Signal Architecture — evaluates active positions for exit conditions.
        
        Returns action: HOLD | EXIT | PARTIAL_EXIT | TRAIL_STOP with reason and urgency.
        """
        try:
            if df_15m is None or df_15m.empty or len(df_15m) < 5:
                return {"action": "HOLD", "reason": "Insufficient data for exit evaluation"}
            
            current_price = float(df_15m['close'].iloc[-1])
            atr = AverageTrueRange(high=df_15m['high'], low=df_15m['low'],
                                   close=df_15m['close'], window=14).average_true_range().iloc[-1]
            ema20 = EMAIndicator(close=df_15m['close'], window=20).ema_indicator().iloc[-1]
            
            # 1. HARD STOP HIT — Immediate exit
            stop_hit = current_price >= stop_loss if is_short else current_price <= stop_loss
            if stop_hit:
                return {"action": "EXIT", "reason": "Stop Loss Hit", "urgency": "IMMEDIATE",
                        "exit_price": current_price}
            
            # 2. TARGET HIT — Partial exit + trail stop to breakeven
            target_hit = current_price <= target if is_short else current_price >= target
            if target_hit:
                new_stop = entry_price - (atr * 0.5) if is_short else entry_price + (atr * 0.5)
                new_target = current_price - (atr * 2.0) if is_short else current_price + (atr * 2.0)
                return {"action": "PARTIAL_EXIT", "reason": "Target Reached — Book 50% + Trail",
                        "urgency": "NEXT_CANDLE", "exit_price": current_price,
                        "new_stop": round(new_stop, 2),
                        "new_target": round(new_target, 2)}
            
            # 3. STRUCTURAL EXIT — Price closes across EMA20 against position
            structural_break = (current_price > ema20 and entry_price < ema20) if is_short else (current_price < ema20 and entry_price > ema20)
            if structural_break:
                pnl_pct = (entry_price - current_price) / entry_price if is_short else (current_price - entry_price) / entry_price
                if pnl_pct > -0.005:  # Still near breakeven
                    return {"action": "EXIT", "reason": "EMA20 Structural Breakdown",
                            "urgency": "NEXT_CANDLE", "exit_price": current_price}
            
            # 4. TIME-BASED EXIT — Held > 2 hours with < 0.5% gain
            pnl_pct = (entry_price - current_price) / entry_price if is_short else (current_price - entry_price) / entry_price
            if entry_time:
                # [V40 GAP#9 FIX] IST-consistent time comparison
                # Old: datetime.utcnow() vs potentially naive entry_time could be off by 5.5h
                ist = pytz.timezone('Asia/Kolkata')
                now_ist = datetime.now(ist)
                if entry_time.tzinfo is None:
                    entry_ist = pytz.utc.localize(entry_time).astimezone(ist)
                else:
                    entry_ist = entry_time.astimezone(ist)
                hold_duration = (now_ist - entry_ist).total_seconds() / 3600
                if hold_duration > 2.0 and pnl_pct < 0.005:
                    return {"action": "EXIT", "reason": f"Time Decay Exit ({hold_duration:.1f}h held, {pnl_pct*100:.2f}% gain)",
                            "urgency": "NEXT_CANDLE", "exit_price": current_price}
            
            # 5. PROGRESSIVE TRAILING STOP — [AUDIT GAP-D ENHANCEMENT]
            # Multi-tier system: locks in more profit as the trade runs further
            # Tier 1 (+0.5R): Lock breakeven — eliminate loss risk on winning trades
            # Tier 2 (+1.0R): Trail with 1.2 ATR cushion — standard institutional trail
            # Tier 3 (+2.0R): Tight trail with 0.8 ATR — lock most profit on runners
            unrealized_r = (entry_price - current_price) / max(atr, 1e-6) if is_short else (current_price - entry_price) / max(atr, 1e-6)
            
            if unrealized_r > 0.5:
                if is_short:
                    breakeven = entry_price * 0.9985  # Breakeven + spread (0.15%)
                    
                    if unrealized_r >= 2.0:
                        # Tier 3: Tight trail (0.8 ATR) — lock in most profit on runners
                        dynamic_trail = current_price + (atr * 0.8)
                        new_stop = min(stop_loss, min(breakeven, dynamic_trail))
                    elif unrealized_r >= 1.0:
                        # Tier 2: Standard trail (1.2 ATR) — institutional standard
                        dynamic_trail = current_price + (atr * 1.2)
                        new_stop = min(stop_loss, min(breakeven, dynamic_trail))
                    else:
                        # Tier 1: Just lock breakeven — eliminate loss
                        new_stop = min(stop_loss, breakeven)
                    
                    trail_triggered = new_stop < stop_loss
                else:
                    breakeven = entry_price * 1.0015  # Breakeven + spread (0.15%)
                    
                    if unrealized_r >= 2.0:
                        # Tier 3: Tight trail (0.8 ATR) — lock in most profit on runners
                        dynamic_trail = current_price - (atr * 0.8)
                        new_stop = max(stop_loss, max(breakeven, dynamic_trail))
                    elif unrealized_r >= 1.0:
                        # Tier 2: Standard trail (1.2 ATR) — institutional standard
                        dynamic_trail = current_price - (atr * 1.2)
                        new_stop = max(stop_loss, max(breakeven, dynamic_trail))
                    else:
                        # Tier 1: Just lock breakeven — eliminate loss
                        new_stop = max(stop_loss, breakeven)
                    
                    trail_triggered = new_stop > stop_loss
                    
                if trail_triggered:
                    tier_label = "T3-Tight" if unrealized_r >= 2.0 else ("T2-Standard" if unrealized_r >= 1.0 else "T1-Breakeven")
                    return {"action": "TRAIL_STOP", "reason": f"Trailing Stop {tier_label} ({unrealized_r:.1f}R profit)",
                            "urgency": "UPDATE", "new_stop": round(new_stop, 2)}
            
            dist_to_tgt = (current_price - target) / current_price if is_short else (target - current_price) / current_price
            dist_to_sl = (stop_loss - current_price) / current_price if is_short else (current_price - stop_loss) / current_price
            return {"action": "HOLD", "reason": "Setup intact",
                    "unrealized_r": round(unrealized_r, 2),
                    "distance_to_target_pct": round(dist_to_tgt * 100, 2),
                    "distance_to_stop_pct": round(dist_to_sl * 100, 2)}
        except Exception as e:
            return {"action": "HOLD", "reason": f"Exit eval error: {str(e)}"}

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
        
        from app.services.kite_data import kite_data
        await kite_data.initialize()
        
        # [V13.5] Bulk Bootstrap liquidity for all symbols in the current scan
        all_symstr = [s["symbol"] if isinstance(s, dict) else s for s in symbols]
        
        # [V23 FIX #8] Liquidity Bootstrap Race Condition Fix
        # OLD: Entire bootstrap was fire-and-forget with 2s sleep — first 20% of scan got false -20 penalty
        # NEW: Synchronously bootstrap first 200 symbols, background the rest
        
        self.job_states[job_id] = {"results": [], "failed_symbols": [], "progress": 0, "is_running": True, "pause_requested": False, "main_task": asyncio.current_task()}
        
        # Move progress loop UP here so UI doesn't hang on INITIALIZING for 3 minutes during proxy validation
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))
        
        # Force a UI update to tell the user what's happening
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.job import Job
            from sqlalchemy import select
            async with AsyncSessionLocal() as session:
                q = select(Job).where(Job.id == job_id)
                res = await session.execute(q)
                j = res.scalars().first()
                if j:
                    j.result = {"status_msg": "Bootstrapping Proxies & Liquidity (Takes ~1 min)...", "progress": 0, "total": total}
                    await session.commit()
        except: pass

        first_batch = all_symstr[:200]
        remaining_batch = all_symstr[200:]
        await liquidity_service.bulk_bootstrap(first_batch)
        if remaining_batch:
            asyncio.create_task(liquidity_service.bulk_bootstrap(remaining_batch))
        index_ctx = await self._get_index_context()
        
        # [V18 FIX #6] Pre-compute sector heat ONCE globally (not per-batch)
        try:
            sector_heat_static = await market_service.get_sector_performances()
            # [V2] get_sector_performances now returns {"1d": float, "5d": float} per sector
            # Convert 1d percentage to decimal for compatibility with gating thresholds
            sector_heat = {}
            for k, v in sector_heat_static.items():
                if isinstance(v, dict):
                    sector_heat[k] = v.get("1d", 0.0) / 100.0
                else:
                    sector_heat[k] = v / 100.0  # Backward compatibility
        except Exception as e:
            print(f"[SECTOR] Failed to fetch global sector heat: {e}")
            sector_heat = {}
        
        # [V31 GAP#8] Track live sector changes from batch data to merge with static
        live_sector_returns = {}  # sector -> [list of intraday returns]

        # R4-8 FIX: Pre-build O(1) index lookup instead of O(n) symbols.index() per stock
        symbol_index_map = {(s["symbol"] if isinstance(s, dict) else s): i for i, s in enumerate(symbols)}

        try:
            # Process in Streaming Batches of 150 for slightly faster turnaround
            chunk_size = 150
            chunks = [symbols[i:i + chunk_size] for i in range(0, total, chunk_size)]
            for i, chunk in enumerate(chunks):
                if job_id in self.job_states and not self.job_states[job_id].get("is_running", True):
                    if logger: logger.warning(f"[STOP] [INTRA] Stop Signal Received. Terminating job {job_id} at {i}/{total}.")
                    break

                # [V12.1 PAUSE CHECK] ️
                while job_id in self.job_states and self.job_states[job_id].get("pause_requested"):
                    if not self.job_states[job_id].get("is_running", True): break
                    await asyncio.sleep(1)

                if not self.job_states[job_id]["is_running"]: break

                chunk_syms = [s['symbol'] if isinstance(s, dict) else s for s in chunk]
                print(f"[SCAN] Pulse Scan: {len(chunk_syms)} symbols")
                
                # 1. Fetch data for this specific batch (with 120s HARD TIMEOUT)
                try:
                    from app.services.kite_data import kite_data
                    print(">> Awaiting asyncio.wait_for(gather(...))")
                    res_15m, res_1h, res_1d, res_prices, res_depth = await asyncio.wait_for(
                        asyncio.gather(
                            market_service.get_batch_ohlc(chunk_syms, interval="15m", period="7d"),
                            market_service.get_batch_ohlc(chunk_syms, interval="60m", period="15d"),
                            market_service.get_batch_ohlc(chunk_syms, interval="1d", period="3mo"),  # V16 FIX 4: Daily trend data
                            market_service.get_batch_prices(chunk_syms),
                            kite_data.get_market_depth(chunk_syms),  # [GAP-C] Real L2 order flow
                        ),
                        timeout=120.0
                    )
                    print(">> Finished asyncio.wait_for!")
                except asyncio.TimeoutError:
                    print(f"[TIMEOUT] Batch {i} hung. Force-skipping to maintain engine flow.")
                    self.job_states[job_id]["progress"] += len(chunk)
                    continue
                except Exception as e:
                    print(f" [ENGINE] Batch {i} crashed: {e}")
                    continue

                print(">> Starting TA computation")
                ta_start = time.time()

                # [V21.1 FIX] Data Quality Audit Per Batch
                empty_count = sum(1 for s in chunk_syms if res_15m.get(s) is None or (hasattr(res_15m.get(s), 'empty') and res_15m[s].empty))
                short_count = sum(1 for s in chunk_syms if res_15m.get(s) is not None and hasattr(res_15m.get(s), '__len__') and 0 < len(res_15m[s]) < 100)
                if empty_count > len(chunk_syms) * 0.3:
                    print(f"️ [DATA QUALITY] Batch {i}: {empty_count}/{len(chunk_syms)} symbols returned EMPTY 15m data!")
                if short_count > 0:
                    print(f"️ [DATA QUALITY] Batch {i}: {short_count} symbols have <100 15m candles (degraded indicators)")
                if res_depth:
                    print(f" [KITE DEPTH] Batch {i}: {len(res_depth)} symbols with L2 order flow data")

                batch_pulse = {}
                for s in chunk_syms:
                    pulse_entry = {"15m": res_15m.get(s), "1h": res_1h.get(s), "1d": res_1d.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}
                    # [AUDIT GAP-C] Inject Kite market depth into pulse data
                    depth_info = res_depth.get(s) if res_depth else None
                    if depth_info:
                        pulse_entry["kite_depth"] = depth_info
                    batch_pulse[s] = pulse_entry

                # [V31 GAP#1 FIX] Build time-of-day RVOL benchmarks from 15m data
                # This runs opportunistically during the scan — zero extra network cost
                # After first batch, subsequent stocks get accurate time-bucket RVOL
                try:
                    liquidity_service.build_time_benchmarks_from_15m(res_15m)
                except Exception:
                    pass
                
                # [V31 GAP#8 FIX] Compute live intraday sector heat from batch data
                # Supplements the static sector index data with actual stock-level performance
                try:
                    for s in chunk_syms:
                        df_s = res_15m.get(s)
                        if df_s is not None and not df_s.empty and len(df_s) >= 2:
                            sector = market_service.get_sector_for_symbol(s)
                            if sector != "General":
                                # Intraday return: current close vs first candle open
                                intra_open = float(df_s['open'].iloc[0])
                                intra_close = float(df_s['close'].iloc[-1])
                                if intra_open > 0:
                                    intra_ret = (intra_close - intra_open) / intra_open
                                    if sector not in live_sector_returns:
                                        live_sector_returns[sector] = []
                                    live_sector_returns[sector].append(intra_ret)
                except Exception:
                    pass
                
                # [V35 GAP#5 FIX] Merge live sector data after EVERY batch, not just batch 0
                # OLD: i == 0 only → 95% of stocks used stale static sector heat
                if live_sector_returns:
                    for sec, rets in live_sector_returns.items():
                        if len(rets) >= 3:  # Need at least 3 stocks for statistical validity
                            live_heat = sum(rets) / len(rets)
                            # Weighted merge: 60% live intraday, 40% static daily
                            static_val = sector_heat.get(sec, 0.0)
                            sector_heat[sec] = (live_heat * 0.6) + (static_val * 0.4)
                    if i % 500 == 0:  # Log every 5th batch to avoid spam
                        print(f"️ [SECTOR HEAT] Live merge: {', '.join(f'{k}={v*100:.1f}%' for k,v in sector_heat.items() if v != 0)}")

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
                                        skip_msg = res.get('skip_reason')
                                        if not skip_msg:
                                            skip_msg = f"Score {res.get('score', 0)} < 50 (System Floor)"
                                        logger.info(f"SKIP {sym}: {skip_msg}")
                                    else:
                                        # [V13] INSTITUTIONAL LOG TRACE
                                        flags = [k for k, v in res.get("flags", {}).items() if v]
                                        flag_str = "|".join(flags) if flags else "None"
                                        msg = f"{sym:10} | Score:{res['score']:>4} | RS:{res.get('rs_alpha', 0):>6.4f} | Regime:{res['regime']:10} | Mode:{res['mode']:10} | Flags:[{flag_str}]"
                                        logger.info(msg)
                                        # Institutional detail logging
                                        if catalysts or penalties:
                                            print(f"   ├  Catalysts: {', '.join(catalysts[:4])}") if catalysts else None
                                            print(f"   ├ ️ Penalties: {', '.join(penalties[:4])}") if penalties else None
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
            # [V32 P7 FIX] Reduced from 80 to 75 — 80 killed ALL signals during chop
            dynamic_floor = 75   # Only high conviction survives, but not zero signals
        else:
            dynamic_floor = self.CONFIG["score_floor"]  # Standard 65
        
        # [V23 FIX #17] VIX-Based Capital Throttle — reduce exposure in volatile markets
        # [V26 V6-FIX 1] Defensive Fail-Closed (15 to 25)
        india_vix = self.system_state.get("india_vix", 25)
        if india_vix > 25:
            dynamic_floor = max(dynamic_floor, 75)  # Only highest conviction
        elif india_vix > 20:
            dynamic_floor = max(dynamic_floor, 70)
        
        filtered = [r for r in raw_results if r.get("score", 0) >= dynamic_floor]
        
        # We also want to keep some holds and sells for the UI so they don't vanish!
        holds = [r for r in raw_results if 50 <= r.get("score", 0) < dynamic_floor]
        sells = [r for r in raw_results if r.get("score", 0) < 50]
        
        # Sort them independently
        filtered = sorted(filtered, key=lambda x: (x.get("priority", 0), x.get("flags", {}).get("FOOTPRINT", 0)), reverse=True)
        holds = sorted(holds, key=lambda x: x.get("score", 0), reverse=True)
        sells = sorted(sells, key=lambda x: x.get("score", 0), reverse=False) # Lowest score is strongest sell
        
        # [V25 V5-FIX 2] Trade Density Matrix (Hard Top-15 correlation cap limit)
        # [V35 GAP#6 FIX] Increased from 15% to 25% — 15% was too restrictive for healthy scans
        top_n_target = min(15, max(5, int(len(filtered) * 0.25)))
        
        # [V23 FIX #17] Halve signal count in extreme volatility
        if india_vix > 25:
            top_n_target = max(3, top_n_target // 2)
        
        # 3. Final Sorting (Priority DESC, Footprint Tie-Break)
        # We use a small epsilon for priority tie-breaking
        all_sorted = filtered[:50] + holds[:20] + sells[:20]
        
        # F8 FIX: Sector Concentration Position Sizing limits
        sector_counts = {}
        for r in all_sorted:
            sym = r["symbol"]
            sector = market_service.get_sector_for_symbol(sym)
            if sector != "General":
                sector_counts[sector] = sector_counts.get(sector, 0) + 1
                # If sector has 3+ positions, cut subsequent sizing by 50%
                if sector_counts[sector] > 2:
                    current_size = r.get("position_size", 0)
                    r["position_size"] = max(1, current_size // 2)
                    r["reasons"].append({"text": f"Warning: Sector Concentration limit hit ({sector} > 2) - Size reduced 50%", "impact": 0, "layer": 3, "type": "negative"})
        
        # [V30 FIX] NON-DESTRUCTIVE ALLOCATION
        # OLD: results = all_sorted[:top_n_target] — destroyed 95% of data on completion,
        #      causing the "vanishing stocks" UI bug where 500 stocks visible during scan
        #      were replaced with only 5-15 after worker saved the final result.
        # NEW: Return ALL filtered results for UI display, but tag the top N as 'recommended'
        #      for execution priority. System state sync uses only recommended set.
        recommended = all_sorted[:top_n_target]
        
        # --- AI BRAIN: FINAL GATEKEEPER (INTRADAY MODE) ---
        from app.services.ai_brain import ai_brain
        if recommended and ai_brain.is_enabled:
            approved_recommended = []
            eval_index = 0
            
            async def analyze_single_setup(setup):
                indicators = {
                    "mode": setup.get("mode"),
                    "regime": setup.get("regime"),
                    "score": setup.get("score"),
                    "l2_footprint": setup.get("flags", {}),
                    "relative_volume": setup.get("liquidity", {}).get("rvol", 1.0)
                }
                return await ai_brain.analyze_trade_setup(
                    setup["symbol"], setup.get("mode", "UNKNOWN"), setup["price"], indicators, setup.get("reasons", []), mode="intraday"
                )

            while len(approved_recommended) < 10 and eval_index < len(recommended):
                needed = 10 - len(approved_recommended)
                batch = recommended[eval_index:eval_index + needed]
                
                print(f"[AI BRAIN] Evaluating {len(batch)} setups (need {needed} more to reach 10)...", flush=True)
                if logger: logger.info(f"[AI BRAIN] Evaluating {len(batch)} setups (need {needed} more to reach 10)...")
                
                ai_tasks = [analyze_single_setup(setup) for setup in batch]
                ai_results = await asyncio.gather(*ai_tasks)
                
                for setup, ai_res in zip(batch, ai_results):
                    setup["ai_confidence"] = ai_res.get("ai_confidence", 0)
                    setup["ai_reason"] = ai_res.get("ai_reason", "AI Engine Error")
                    setup["ai_approved"] = ai_res.get("approved", True)
                    
                    if not setup["ai_approved"]:
                        print(f"  [X] AI VETOED {setup['symbol']}: {setup['ai_reason']}", flush=True)
                        if logger: logger.warning(f"[X] AI VETOED {setup['symbol']}: {setup['ai_reason']}")
                        setup["reasons"].append({"text": f"[AI REJECTED] {setup['ai_reason']}", "impact": -30, "layer": 3, "type": "negative"})
                        setup["score"] = max(0, setup["score"] - 30) # Demote score
                        # Re-calculate signal to ensure it drops out of the BUY category
                        setup["signal"] = self._get_signal(setup["score"], setup.get("mode", "NONE"))
                    else:
                        print(f"  [] AI APPROVED {setup['symbol']}: {setup['ai_confidence']}/100", flush=True)
                        if logger: logger.info(f"[] AI APPROVED {setup['symbol']}: {setup['ai_confidence']}/100")
                        approved_recommended.append(setup)
                
                eval_index += len(batch)
            
            # Reconstruct recommended: all AI approved + any remaining setups that were NOT sent to the AI
            recommended = approved_recommended + recommended[eval_index:]
        
        recommended_symbols = {r["symbol"] for r in recommended}
        
        for r in all_sorted:
            r["recommended"] = r["symbol"] in recommended_symbols
        
        # 4. System State Synchronization (uses only recommended set for risk calibration)
        self._sync_scans_and_risk(recommended)
        
        # 5. Cross-Scan Persistence Update (uses only recommended set)
        for res in recommended:
            sym = res["symbol"]
            if sym not in self.persistence_cache: self.persistence_cache[sym] = []
            self.persistence_cache[sym].append({"score": res["score"], "time": datetime.utcnow()})
            # Keep only last 5 scans
            if len(self.persistence_cache[sym]) > 5: self.persistence_cache[sym].pop(0)

        self._save_persistence_cache()

        # [V29 V9-FIX 3] Unbounded Memory Growth (Persistence Eviction)
        current_symbols = {res["symbol"] for res in recommended}
        stale_keys = [k for k in self.persistence_cache if k not in current_symbols]
        for k in stale_keys:
            # Only evict if the last entry is older than 30 minutes
            last_entry = self.persistence_cache[k][-1] if self.persistence_cache[k] else None
            if last_entry and (datetime.utcnow() - last_entry["time"]).total_seconds() > 1800:
                del self.persistence_cache[k]

        return sanitize_data({
            "total": total, 
            "success": len(all_sorted), 
            "recommended_count": len(recommended),
            "system_state": self.system_state,
            "data": all_sorted
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
                        # [V12.1 EXTERNAL CANCEL CHECK] 
                        if job.status in ["failed", "cancelled", "stopped"]:
                            state["is_running"] = False
                            # [V12.2] Explicitly cancel the main execution task
                            main_task = state.get("main_task")
                            if main_task and not main_task.done():
                                main_task.cancel()
                            break
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ️
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

    def _save_persistence_cache(self):
        import json, os
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "persistence_cache.json")
        try:
            serializable = {}
            for k, v in self.persistence_cache.items():
                serializable[k] = [{"score": e["score"], "time": e["time"].isoformat()} for e in v]
            with open(cache_path, "w") as f:
                json.dump(serializable, f)
        except Exception: 
            pass

    def _load_persistence_cache(self):
        import json, os
        from datetime import datetime
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "persistence_cache.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r") as f:
                    data = json.load(f)
                for k, v in data.items():
                    self.persistence_cache[k] = [{"score": e["score"], "time": datetime.fromisoformat(e["time"])} for e in v]
            except Exception:
                pass

intraday_engine = IntradayEngine()
