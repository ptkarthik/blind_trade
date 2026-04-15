import asyncio
import pandas as pd
import numpy as np
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
        
        # FIX #2: Removed 13 dead SCORING_FLAGS that were never checked.
        # Only enable_mtf_bonus (used at Line 109) is kept.
        self.SCORING_FLAGS = {
            "enable_mtf_bonus": True
        }

    async def _get_index_context(self):
        """[V11 RESTORED] Complex Market Regime Audit."""
        try:
            nifty_df = await market_service.get_ohlc("^NSEI", period="2d", interval="5m")
            if nifty_df is None or nifty_df.empty: 
                return {"score": 50, "market_regime": "Mixed", "ad_ratio": 1.0, "day_change_pct": 0.0}
            
            close = nifty_df['close'].iloc[-1]
            vwap = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap(nifty_df)
            ad_ratio = await market_service.get_advance_decline_ratio()
            sector_perfs = await market_service.get_sector_performances()
            
            # [V12.7] Sideways Detection
            adx_ctx = ta_intraday.IntradayTechnicalAnalysis.calculate_adx(nifty_df)
            is_sideways = adx_ctx.get("adx", 0) < 20
            
            regime = "Strong Bullish" if close > vwap and ad_ratio > 1.2 else "Mixed"
            if close < vwap and ad_ratio < 0.8: regime = "Strong Bearish"

            return {
                "market_trend": "Bullish" if close > vwap else "Bearish",
                "market_regime": regime,
                "is_sideways": is_sideways,
                "ad_ratio": ad_ratio, "sector_perfs": sector_perfs,
                "day_change_pct": round(((close - nifty_df['open'].iloc[0])/nifty_df['open'].iloc[0])*100, 2)
            }
        except: return {"score": 50, "market_regime": "Mixed", "is_sideways": False, "ad_ratio": 1.0, "day_change_pct": 0.0}

    async def analyze_stock(self, sym: str, job_id: str = None, global_index_ctx: dict = None, pulse_data: dict = None):
        """
        [V11 RESTORED] Full 12-Point Alpha Audit.
        Integrated with Layer 1, 2, and 3 logic.
        """
        try:
            # 1. DATA EXTRACTION
            df_15m = None
            df_1h = None
            real_price = 0.0

            if pulse_data and sym in pulse_data:
                item = pulse_data[sym]
                if isinstance(item, pd.DataFrame):
                    df_15m = item
                elif isinstance(item, dict):
                    df_15m = item.get("15m")
                    df_1h = item.get("1h")
                
                if df_15m is not None and not df_15m.empty:
                    real_price = float(df_15m['close'].iloc[-1])
            else:
                # Fallback to direct fetch
                df_15m = await market_service.get_ohlc(sym, period="7d", interval="15m")
                if self.SCORING_FLAGS.get("enable_mtf_bonus"):
                    df_1h = await market_service.get_ohlc(sym, period="15d", interval="60m")
                pinfo = await market_service.get_live_price(sym)
                real_price = pinfo.get("price", 0.0)

            if df_15m is None or df_15m.empty or len(df_15m) < 20:
                return {"symbol": sym, "skip_reason": "Data Depleted"}
            
            if real_price <= 0:
                real_price = float(df_15m['close'].iloc[-1])
            if real_price <= 0:
                return {"symbol": sym, "skip_reason": "Price Invalid (0.0)"}

            # =========================
            # STEP 1: INDICATORS
            # =========================
            if df_1h is None or df_1h.empty:
                df_1h = await market_service.get_ohlc(sym, period="15d", interval="60m")

            indicators = self._get_indicators(df_15m, df_1h)
            if indicators is None:
                return {"symbol": sym, "skip_reason": "Indicator Failure (NaN)"}

            # V16 AUDIT FIX 4: Daily (1D) Macro Trend Filter
            # Prevents buying 15m bounces on stocks in catastrophic daily downtrends
            is_1d_bullish = True  # Default: bullish (fail-open if data unavailable)
            df_1d = None
            if pulse_data and sym in pulse_data and isinstance(pulse_data[sym], dict):
                df_1d = pulse_data[sym].get("1d")
            if df_1d is None:
                try:
                    df_1d = await market_service.get_ohlc(sym, period="3mo", interval="1d")
                except Exception:
                    pass
            if df_1d is not None and not df_1d.empty and len(df_1d) >= 20:
                try:
                    daily_ema20 = EMAIndicator(close=df_1d['close'], window=20).ema_indicator().iloc[-1]
                    is_1d_bullish = real_price > float(daily_ema20)
                except Exception:
                    pass
            indicators["is_1d_bullish"] = is_1d_bullish

            # SMART GATE: Allow analysis if price is below EMA20 BUT has high-conviction reclaim
            is_below_ema = indicators["price"] < indicators["ema20"]
            # P6 FIX: Smart Gate now uses MAJORITY VOTE (2 of 3) instead of OR (any 1 of 3)
            # OLD: OR logic let panic-selling stocks through on RVOL alone (distribution volume)
            # NEW: require at least 2 conviction signals to confirm this is accumulation, not distribution
            conviction_signals = [
                indicators.get("rvol", 0) > 2.0,                                    # Institutional volume
                indicators["price"] > indicators.get("vwap_val", 0) * 1.005,         # Above VWAP by 0.5%
                indicators.get("pa_score", 0) > 80                                   # Aggressive buying candle
            ]
            has_reclaim_conviction = sum(conviction_signals) >= 2

            # R4-1 FIX: Explicitly mark Smart Gate bypass so L3 and future code knows
            # this stock is below EMA20 but was allowed through on conviction signals.
            # Without this flag, a refactor removing L3's below-EMA penalty would silently break protection.
            if is_below_ema and has_reclaim_conviction:
                indicators["smart_gate_bypass"] = True

            if is_below_ema and not has_reclaim_conviction:
                liq = liquidity_service.get_liquidity(sym)
                return {
                    "symbol": sym,
                    "price": round(real_price, 2),
                    "score": 0,
                    "signal": "IGNORE",
                    "signal_label": "IGNORE",
                    "verdict": "Below EMA20",
                    "reason": "Below EMA20 (No Reclaim Conviction)",
                    "alpha_mode": "NONE",
                    "entry": round(real_price, 2),
                    "target": 0.0,
                    "stop_loss": 0.0,
                    "tradability": {},
                    "reasons": [],
                    "groups": {
                        "DNA (40%)": {"score": 0, "max": 40, "details": []},
                        "Alpha Edge (60%)": {"score": 0, "max": 60, "details": []},
                        "Safeguards (L3)": {"score": 0, "max": 0, "details": []}
                    },
                    "liquidity": {
                        "level": liq.get("level", "Unknown"),
                        "adv20": liq.get("adv20", 0),
                        "max_stealth_buy_qty": 0,
                        "max_stealth_buy_value": 0
                    }
                }

            # =========================
            # STEP 2: LAYER 1 (DNA)
            # =========================
            l1_score, l1_data = self._run_layer1(indicators)

            # =========================
            # STEP 3: DNA GATE (V14.1: Calibrated Floor)
            # =========================
            # OLD: floor was 13, blocking stocks with slope(10) + small RVOL(6) = 16
            # NEW: floor is 10, allowing early momentum (slope only) through for L2 analysis
            # Recovery Bonus: if RVOL > 2.0 (Institutional), bypass gate entirely
            rvol_bypass = indicators.get("rvol", 0) > 2.0
            if l1_score < 10 and not rvol_bypass:
                l2_score = 0
                # FIX M3: Use 'mode' key consistently (was 'alpha_mode') so EXHAUSTED check works
                l2_data = {"mode": "NONE", "alpha_mode": "NONE", "reason": "DNA Gate Blocked"}
                liq = liquidity_service.get_liquidity(sym) # Fast check for ignored
                # P14 FIX: Skip L3 for DNA-blocked stocks — penalties are meaningless when score is already 0
                l3_penalty = 0; l3_data = {"penalty": 0, "reasons": []}
            else:
                # [V13.1] Lazy-load liquidity for high-conviction candidates
                liq = await liquidity_service.get_liquidity_async(sym)
                
                # P5/P13 FIX: Pass df_15m to _run_layer2 so signals are computed AFTER exhaustion check
                l2_score, l2_data = self._run_layer2(indicators, df_15m)

            # =========================
            # STEP 4: LAYER 3
            # =========================
            # P14: Only run L3 if stock passed DNA gate (l3 already set to 0 above for blocked stocks)
            if l1_score >= 10 or rvol_bypass:
                l3_penalty, l3_data = self._run_layer3(indicators, df_15m, global_index_ctx, l2_data, liq=liq)

            # =========================
            # FINAL SCORE
            # =========================
            # R4-5 FIX: Cap L3 penalty at 75% of (L1+L2) to prevent wiping valid setups
            # OLD: L3 max = 125, L1+L2 max = 100 → even perfect setups zeroed
            # NEW: A truly strong setup (40+60=100) can lose at most 75 pts from L3
            effective_l3 = min(l3_penalty, int((l1_score + l2_score) * 0.75))
            final_score = max(0, min(100, (l1_score + l2_score - effective_l3)))
            signal = self._get_signal(final_score)

            # [V12.9] Institutional Liquidity Analysis (already fetched above)
            adv20 = liq.get("adv20", 0)
            liq_level = liq.get("level", "Unknown")
            # 1% Stealth Limit
            max_qty = int(adv20 * 0.01) if adv20 > 0 else 0
            max_value = round(max_qty * real_price, 0)

            # Compatibility: build "reasons" list and "groups" for UI
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

            verdict = "PIONEER PRIME" if final_score >= 85 else "Standard Setup"
            signal_label = f"{signal} {('🏆' if final_score > 85 else '✅')}"
            
            if l2_data.get("mode") == "EXHAUSTED":
                verdict = "AVOID - Overextended"
                signal = "IGNORE"
                signal_label = "EXHAUSTED 🛑"

            # =========================
            # STEP 5: TRADABILITY
            # =========================
            kite_audit = kite_service.get_tradability(sym)

            return {
                "symbol": sym, 
                "price": round(real_price, 2), 
                "score": round(final_score, 1),
                "signal": signal, 
                "signal_label": signal_label, 
                "verdict": verdict,
                "tradability": kite_audit,
                "reasons": reasons,
                "groups": groups,
                "entry": round(real_price, 2),
                # V14.6 FIX: Pipe dynamic structural targets natively from the advanced models if available
                "target": l2_data.get("dynamic_zones", {}).get("target") or round(real_price + max(indicators.get("atr", 0) * (2.5 if indicators.get("rvol", 0) > 2.5 else (2.0 if indicators.get("rvol", 0) > 1.2 else 1.5)), real_price * 0.0075), 2),
                "stop_loss": l2_data.get("dynamic_zones", {}).get("stop_loss") or round(real_price - max(indicators.get("atr", 0) * 1.5, real_price * 0.005), 2),
                # V16 AUDIT FIX 3: Position Allocation with safety caps
                # Risk parity: 1% max risk on 100k capital baseline (₹1,000 risk per trade)
                # Guards: (a) max ₹1L total exposure, (b) never exceed 1% of ADV20 (stealth limit)
                "position_size": min(
                    int(1000 / max(abs(real_price - (l2_data.get("dynamic_zones", {}).get("stop_loss") or round(real_price - max(indicators.get("atr", 0) * 1.5, real_price * 0.005), 2))), 0.01)),
                    int(100000 / max(real_price, 1)),     # Cap: ₹1 Lakh max exposure
                    max(int(adv20 * 0.01), 1) if adv20 > 0 else int(100000 / max(real_price, 1))  # Cap: 1% of ADV20
                ),
                "alpha_mode": l2_data.get("mode", "NONE"),
                "liquidity": {
                    "level": liq_level,
                    "adv20": adv20,
                    "max_stealth_buy_qty": max_qty,
                    "max_stealth_buy_value": max_value
                }
            }
        except Exception as e:
            return {"symbol": sym, "skip_reason": f"Analysis Error: {str(e)}"}

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
                    pb_engine = ta_intraday.IntradayTechnicalAnalysis.detect_pullback_entry_v45(df_15m, indicators.get("vwap_val", price))
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
            alpha_mode = "PULLBACK"; score += pb_score; reasons.append({"text": pb_reason, "impact": pb_score})
            
        # 2C. Momentum Phase
        elif is_trending and distance_vwap > 1.2 and rvol > 1.5:
            alpha_mode = "MOMENTUM"; score += 40; reasons.append({"text": "MOMENTUM: Strong trend + volume", "impact": 40})
            
        # 2D. Early Phase Base (Catch-all for standard healthy setups that aren't explosive yet)
        elif is_near_vwap and is_trending and structure_ok:
            alpha_mode = "EARLY"; score += 45; reasons.append({"text": "EARLY: Near VWAP + Trend + Structure", "impact": 45})
            
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
                    # Lunch Chop Filter (11:30 to 13:30)
                    if (h == 11 and m >= 30) or h == 12 or (h == 13 and m <= 30):
                        penalty += 20; reasons.append({"text": "Penalty: Lunch Chop Zone (Time Decay)", "impact": -20})
                    # V16 AUDIT FIX 2: EOD Liquidation Risk Filter (After 14:45, including 15:00-15:30)
                    # OLD: only h==14, m>=45 — missed the entire 15:00-15:30 window
                    elif (h == 14 and m >= 45) or h >= 15:
                        penalty += 30; reasons.append({"text": "Penalty: End Of Day Liquidation Risk", "impact": -30})
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
        # This prevents the "500 Shares" loop by pre-loading volume data in batches
        all_symstr = [s["symbol"] if isinstance(s, dict) else s for s in symbols]
        asyncio.create_task(liquidity_service.bulk_bootstrap(all_symstr))
        
        self.job_states[job_id] = {"results": [], "failed_symbols": [], "progress": 0, "is_running": True, "pause_requested": False, "main_task": asyncio.current_task()}
        index_ctx = await self._get_index_context()
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

                # 2. Analyze the batch immediately
                async def sem_task(s_obj):
                    sym = s_obj["symbol"] if isinstance(s_obj, dict) else s_obj
                    async with self.semaphore:
                        try:
                            # [PER-STOCK LOGGING REQUESTED]
                            res = await asyncio.wait_for(
                                self.analyze_stock(sym, job_id, index_ctx, batch_pulse),
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
                                        reason_text = res.get('reason')
                                        if not reason_text:
                                            details = res.get('groups', {}).get('Alpha Edge (60%)', {}).get('details', [])
                                            reason_text = details[0].get('text', 'Gate Blocked') if details else 'Gate Blocked'
                                        
                                        if isinstance(reason_text, dict): 
                                            reason_text = reason_text.get('text', 'Unknown')
                                        
                                        logger.info(f"SKIP {sym}: {reason_text}")
                                    else:
                                        # COMPACT INSTITUTIONAL LOGGING
                                        msg = f"OK {sym}: {res['score']:>3} | {res['signal']} | L1:{l1} L2:{l2} L3:{l3} | Cap:{cap_str}"
                                        logger.info(msg)
                                        # Keep catalysts/penalties in stdout (print) but omit from system_logger info to save space
                                        print(f"   └ 🚀 Catalysts: {', '.join(catalysts[:4])}", flush=True) if catalysts else None
                                        print(f"   └ 🛡️ Penalties: {', '.join(penalties[:4])}", flush=True) if penalties else None
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
                
        finally:
            self.job_states[job_id]["is_running"] = False
            await sync_task

        # [V14.6 SEQUENCE-AWARE SORTING] Descending Score, then Ascending Analysis Index
        results = sorted(self.job_states[job_id]["results"], key=lambda x: (x.get("score", 0), -(x.get("analysis_index", 0))), reverse=True)
        return sanitize_data({"total": total, "success": len(results), "data": results})

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
