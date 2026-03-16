import asyncio
import pandas as pd
import numpy as np
from app.services.market_data import market_service
from app.services.index_context import index_ctx
from app.services.liquidity_service import liquidity_service
import app.services.ta_intraday as ta_intraday
from app.services.utils import STATIC_FULL_LIST, sanitize_data
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
import pytz
from datetime import datetime, timedelta
from app.core.config import settings

class IntradayEngine:
    """
    Specialized engine for Intraday Analysis.
    Focuses on 15-minute intervals, VWAP, and Momentum.
    """
    def __init__(self):
        self.semaphore = asyncio.Semaphore(10) # Reduced from 15 to prevent yfinance engine collisions
        self.job_states = {} # Stores state per job_id to prevent collisions

    def _group_by_sector(self, results):
        """Pre-groups results by sector for fast UI retrieval."""
        grouped = {}
        for r in results:
            sec = r.get("sector", "General")
            if sec not in grouped:
                grouped[sec] = {"buys": [], "holds": [], "sells": []}
            signal = r.get("signal")
            if signal == "BUY": grouped[sec]["buys"].append(r)
            elif signal == "SELL": grouped[sec]["sells"].append(r)
            else: grouped[sec]["holds"].append(r)
        return grouped

    async def _get_sector_densities(self):
        """
        V6.3: Calculate institutional sector participation density.
        Returns a map: {sector_name: density_percentage}
        """
        try:
            # 1. Get current scan universe (Top ~200 symbols for speed)
            from app.services.market_discovery import market_discovery
            symbols = await market_discovery.get_full_market_list()
            if not symbols: return {}

            # Limit to top 250 for fast density check
            sample_symbols = symbols[:250]
            
            # 2. Batch fetch latest 15m volume for sample
            # This is a 'fast' probe to estimate sector density
            # yf.download is efficient for batches
            import yfinance as yf
            import asyncio
            
            def _fetch_batch():
                # We only need the last candle (15m)
                data = yf.download(sample_symbols, period="1d", interval="15m", progress=False, group_by='ticker')
                return data

            df_batch = await asyncio.to_thread(_fetch_batch)
            if df_batch.empty: return {}

            sector_counts = {} # sector -> {"total": X, "high_vol": Y}
            
            for sym in sample_symbols:
                try:
                    # Sector Density Precision: Only include stocks with ADV20 >= 200k
                    liq_ctx = liquidity_service.get_liquidity(sym)
                    if liq_ctx.get("adv20", 0) < 200000:
                        continue

                    sector = market_service.get_sector_for_symbol(sym)
                    if sector not in sector_counts:
                        sector_counts[sector] = {"total": 0, "high_vol": 0}
                    
                    # Estimate RVOL using last known benchmark
                    if isinstance(df_batch.columns, pd.MultiIndex):
                        ticker_data = df_batch[sym]
                    else:
                        ticker_data = df_batch
                        
                    if ticker_data.empty: continue
                    
                    last_vol = ticker_data['Volume'].iloc[-1]
                    time_bucket = ticker_data.index[-1].strftime("%H:%M")
                    benchmark = liquidity_service.get_benchmark_vol(sym, time_bucket)
                    
                    rvol = last_vol / benchmark if benchmark > 0 else 1.0
                    
                    sector_counts[sector]["total"] += 1
                    if rvol > 1.5:
                        sector_counts[sector]["high_vol"] += 1
                except:
                    continue
            
            densities = {}
            for sector, counts in sector_counts.items():
                if counts["total"] > 0:
                    densities[sector] = counts["high_vol"] / counts["total"]
                else:
                    densities[sector] = 0.0
            
            return densities
        except Exception as e:
            print(f"Error calculating sector densities: {e}")
            return {}

    async def _get_index_context(self):
        """
        Analyze Nifty 50 (market_index) for V3.5 Market Regime Classification.
        Timeframe: 5-minute.
        """
        try:
            # Fetch 5m data for Nifty 50 (^NSEI)
            nifty_task = market_service.get_ohlc("^NSEI", period="2d", interval="5m")
            nifty_df = await asyncio.wait_for(nifty_task, timeout=10.0)
            
            if nifty_df is None or nifty_df.empty or len(nifty_df) < 20: 
                return {"score": 50, "bias": "Neutral", "regime": "Mixed", "day_change_pct": 0.0, "ad_ratio": 1.0, "sector_perfs": {}}

            close = nifty_df['close'].iloc[-1]
            vwap = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap(nifty_df)
            
            # EMA20, EMA50
            ema20 = ta_intraday.EMAIndicator(close=nifty_df['close'], window=20).ema_indicator().iloc[-1]
            ema50 = ta_intraday.EMAIndicator(close=nifty_df['close'], window=50).ema_indicator().iloc[-1]
            
            # ADX(14)
            adx_ind = ta_intraday.ADXIndicator(high=nifty_df['high'], low=nifty_df['low'], close=nifty_df['close'], window=14)
            adx_val = adx_ind.adx().iloc[-1]
            
            # 2. TREND DETECTION
            market_trend = "Neutral"
            if ema20 > ema50 and adx_val > 20:
                market_trend = "Bullish Trend"
            elif ema20 < ema50 and adx_val > 20:
                market_trend = "Bearish Trend"
            
            if adx_val < 18:
                market_trend = "Choppy"
                
            # 3. VWAP CONFIRMATION
            market_bias = "Bullish" if close > vwap else "Bearish"
            
            # 4. MARKET REGIME CLASSIFICATION
            market_regime = "Mixed"
            if market_trend == "Bullish Trend" and market_bias == "Bullish":
                market_regime = "Strong Bullish"
            elif market_trend == "Bearish Trend" and market_bias == "Bearish":
                market_regime = "Strong Bearish"
            elif adx_val < 18:
                market_regime = "Sideways / Choppy"
            
            # Fetch Advance/Decline Ratio & Sectors for context
            ad_ratio = await market_service.get_advance_decline_ratio()
            sector_perfs = await market_service.get_sector_performances()
            
            # V6.3: Get Sector RVOL Densities
            sector_densities = await self._get_sector_densities()
            
            # Day change pct for baseline
            today_date = nifty_df.index[-1].date()
            prev_days_df = nifty_df[nifty_df.index.date < today_date]
            if not prev_days_df.empty:
                prev_close = prev_days_df['close'].iloc[-1]
                day_change_pct = ((close - prev_close) / prev_close) * 100
            else:
                today_open = nifty_df[nifty_df.index.date == today_date]['open'].iloc[0]
                day_change_pct = ((close - today_open) / today_open) * 100

            return {
                "market_trend": market_trend,
                "market_bias": market_bias,
                "market_regime": market_regime,
                "ad_ratio": ad_ratio,
                "sector_perfs": sector_perfs,
                "sector_densities": sector_densities, # Added for V6.3
                "day_change_pct": round(day_change_pct, 2),
                "adx_val": round(adx_val, 2),
                "score": 100 if market_regime == "Strong Bullish" else 0 if market_regime == "Strong Bearish" else 50
            }

        except Exception as e:
            print(f"Error fetching V3.5 Market Regime Index Context: {e}")
            return {"score": 50, "bias": "Neutral", "regime": "Mixed", "day_change_pct": 0.0, "ad_ratio": 1.0, "sector_perfs": {}}

    def _is_optimal_window(self, now_time):
        """
        Classifies current time into V4 Optimal Scan Timing Windows.
        """
        t = now_time.hour * 100 + now_time.minute
        
        # Windows:
        # 09:25–09:35 (925-935)
        # 10:00–10:15 (1000-1015)
        # 11:25–11:35 (1125-1135)
        # 14:25–14:45 (1425-1445)
        
        if (925 <= t <= 935) or (1000 <= t <= 1015) or (1125 <= t <= 1135) or (1425 <= t <= 1445):
            return "OPTIMAL"
        return "NORMAL"

    async def analyze_stock(self, sym: str, job_id: str = None, global_index_ctx: dict = None, fast_fail: bool = False):
        """
        Professional Intraday Analysis with Multi-Timeframe & Market Context.
        """
        try:
            # CHECK STOP 1
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            reasons = [] # INITIALIZE UNIVERSAL REASONS LIST
            
            # --- SCORING INITIALIZATION ---
            pullback_bonus = reclaim_bonus = sweep_bonus = squeeze_bonus = 0
            gap_bonus = poc_bonus = fan_bonus = rvol_bonus = 0
            inst_bonus = mtf_bonus = acc_bonus = accumulation_bonus = 0
            institutional_volume_bonus = trend_bonus = vwap_reclaim_bonus = 0
            trend_dir_bonus = sector_bonus = daily_momentum_bonus = 0
            regime_bonus = ad_bonus = liquidity_bonus = 0
            vwap_bonus = vol_acc_bonus = 0
            liq_accel_bonus = liq_accel_penalty = 0
            volume_validation_state = "PASSED"
            is_volume_block = False
            
            exhaustion_penalty = dev_penalty = context_penalty = 0
            overheat_penalty = chop_penalty = volume_penalty = 0
            structure_penalty = fake_breakout_penalty = vwap_ext_penalty = 0
            trend_penalty = trap_penalty = trend_dir_penalty = 0
            sector_penalty_v6_3 = 0

            # 1. Fetch 30d OHLC for ADV20/RVOL Benchmark & ABSOLUTE LATEST Price
            # We need 30d to ensure we have at least 20 trading days of data
            ohlc_task = market_service.get_ohlc(sym, period="30d", interval="15m", fast_fail=fast_fail)
            live_price_task = market_service.get_latest_price(sym)
            df_hist, live_price = await asyncio.gather(ohlc_task, live_price_task)
            
            if df_hist is None or df_hist.empty or len(df_hist) < 100:
                print(f"⚠️ Intraday Analysis skipped for {sym}: Insufficient historical data.")
                return None
            
            # Attach symbol for ta_intraday to use in LiquidityService lookups
            df_hist.attrs["symbol"] = sym

            # Extract 5m data for the last 3 days for timing and micro-patterns
            df_5m = await market_service.get_ohlc(sym, period="3d", interval="5m", fast_fail=fast_fail)
            if df_5m is None or df_5m.empty: return None
            
            if df_5m is None or df_5m.empty or len(df_5m) < 40:
                print(f"⚠️ Intraday Analysis skipped for {sym}: Insufficient data (5m).")
                return None
            
            # Use Live price if valid, else fallback to latest candle close
            real_price = live_price if live_price > 0 else df_5m['close'].iloc[-1]
            if real_price <= 0: return None

            # 2. Use df_hist (15m) for core technicals
            df_15m = df_hist

            # Ensure only completed candles are used (V6.3 Precision Fix)
            # This prevents unstable calculations from intrabar volume spikes
            now_timing = datetime.now(pytz.timezone(settings.MARKET_TIMEZONE))
            if not df_15m.empty:
                last_15m = df_15m.index[-1]
                if now_timing < last_15m + timedelta(minutes=15):
                    df_15m = df_15m.iloc[:-1]
            
            if not df_5m.empty:
                last_5m = df_5m.index[-1]
                if now_timing < last_5m + timedelta(minutes=5):
                    df_5m = df_5m.iloc[:-1]
                
            if global_index_ctx:
                index_ctx = global_index_ctx
            else:
                index_ctx = await self._get_index_context()

            # CHECK STOP 3
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # --- INSTITUTIONAL INTEL (Bypassed for Speed) ---
            rs_rating = 50
            spon_action = "Neutral"

            # CHECK STOP 4
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None
            
            # 3. Technical Analysis (Intraday Mode)
            ta_15m = ta_intraday.IntradayTechnicalAnalysis.analyze_stock(df_15m)
            sweep = ta_intraday.IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df_15m)
            acc = ta_intraday.IntradayTechnicalAnalysis.detect_smart_money_accumulation(df_15m)
            structure = ta_intraday.IntradayTechnicalAnalysis.detect_market_structure(df_15m)
            trap = ta_intraday.IntradayTechnicalAnalysis.detect_liquidity_trap(df_15m)
            trend_guard = ta_intraday.IntradayTechnicalAnalysis.detect_trend_direction(df_15m)
            if not ta_15m: return None
            
            # 5m Momentum & Entry timing
            ta_5m = await asyncio.to_thread(ta_intraday.analyze_stock, df_5m)
            
            # 1H Multi-Timeframe Confirmation
            mtf_ctx = {"is_bullish": False, "reason": "No 1H Data"} # Defensive fallback: Don't confirm if data missing
            if df_1h is not None and not df_1h.empty:
                ta_1h = await asyncio.to_thread(ta_intraday.analyze_stock, df_1h)
                mtf_ctx = {
                    "is_bullish": ta_1h.get("is_bullish_trend", False),
                    "score": ta_1h.get("vwap_score", 50),
                    "trend": ta_1h.get("trend", "NEUTRAL")
                }
            
            # 4. Professional Weighted Scoring (User 5-Indicator Custom Algorithm)
            vwap_score = ta_15m.get("vwap_score", 50)
            pa_score = ta_15m.get("pa_score", 50)
            pivot_score = ta_15m.get("pivot_score", 50)
            
            # User noted EMAs are best on 1m, 3m, 5m. Use 5m if available
            ema_score = ta_5m.get("ema_score", 50) if ta_5m else ta_15m.get("ema_score", 50)
            
            # ADX Score (Trend Strength)
            adx_score = ta_15m.get("adx_score", 50)
            
            # V3.2 RVOL & ADV Metadata from TA
            rvol_val = ta_15m.get("rvol_val", 1.0)
            adv20 = ta_15m.get("adv20", 0)
            liq_level = ta_15m.get("liq_level", "Unknown")
            
            # MODULE 5 V5: Institutional Volume Confirmation
            vol_ma = df_5m['volume'].rolling(20).mean().iloc[-1]
            current_volume = df_5m['volume'].iloc[-1]
            volume_expansion_ratio = current_volume / vol_ma if vol_ma > 0 else 1.0
            institutional_volume_flag = False
            volume_penalty = 0
            
            # Fix 1: Standardization - Volume guard now uses RVOL 
            if rvol_val < 1.0:
                volume_validation_state = "LOW_VOLUME_BLOCK"
                reasons.append({"text": "Low Volume Validation Block", "type": "negative", "label": "VOLUME", "value": f"{round(rvol_val,2)}x", "impact": 0})
                # Note: Penalty scoring (-25) is handled centrally in Module 2 for rvol < 1.0
            elif volume_expansion_ratio >= 1.8:
                institutional_volume_flag = True
                reasons.append({"text": "Institutional Volume Surge", "type": "positive", "label": "INSTITUTIONAL", "value": f"{round(volume_expansion_ratio,2)}x", "impact": 10})
                # Bonus will be added to base score later

            # MODULE 12 V6: VWAP DEVIATION GUARD
            vwap_val = ta_15m.get("vwap_val", real_price)
            vwap_deviation_pct = ((real_price - vwap_val) / vwap_val * 100) if vwap_val > 0 else 0.0
            vwap_ext_penalty = 0
            if vwap_deviation_pct > 4.0:
                reasons.append({"text": "Critical VWAP Extension", "type": "negative", "label": "RISK", "value": f"{round(vwap_deviation_pct,1)}%", "impact": 0})
            elif vwap_deviation_pct > 2.5:
                vwap_ext_penalty = -20
                reasons.append({"text": "Extended above fair value", "type": "negative", "label": "VWAP", "value": f"{round(vwap_deviation_pct,1)}%", "impact": -20})

            # MODULE 13 V6: TREND MOMENTUM EXPANSION FILTER
            adx_ctx = ta_15m.get("adx_details", {"adx": 0, "is_rising": False, "adx_slope": 0.0})
            adx_val = adx_ctx.get("adx", 0)
            adx_slope = adx_ctx.get("adx_slope", 0)
            trend_penalty = 0
            trend_bonus = 0
            trend_momentum_state = "NEUTRAL"
            
            if adx_val < 18:
                pass # Hard block handled in Signal Classification
            elif adx_val > 25 and adx_slope > 0:
                trend_bonus = 10
                trend_momentum_state = "RISING_STRENGTH"
                reasons.append({"text": "Rising Trend Momentum", "type": "positive", "label": "ADX", "value": f"+{round(adx_slope,2)}", "impact": 10})
            elif adx_slope < 0:
                trend_momentum_state = "FALLING_STRENGTH"
                reasons.append({"text": "Fading Momentum", "type": "neutral", "label": "ADX", "value": f"{round(adx_slope,2)}", "impact": 0})

            # MODULE 14 V6: LIQUIDITY TRAP DETECTOR
            trap_move_detected = trap.get("trap_move_detected", False)
            trap_range_expansion = trap.get("trap_range_expansion", False)
            trap_penalty = 0
            if trap_move_detected:
                trap_penalty = -30
                reasons.append({"text": "Trap Condition Met", "type": "negative", "label": "TRAP", "value": "ALERT", "impact": -30})

            # MODULE 5 V6.2: TREND DIRECTION GUARD
            trend_direction_state = trend_guard.get("trend_direction_state", "NEUTRAL_TREND")
            ema_alignment = trend_guard.get("ema_alignment", False)
            trend_dir_penalty = 0
            trend_dir_bonus = 0
            if trend_direction_state == "BEARISH_TREND":
                trend_dir_penalty = -25
                reasons.append({"text": "Bearish Trend Guard (EMA 20/50)", "type": "negative", "label": "TREND", "value": "BEARISH", "impact": -25})
            elif trend_direction_state == "BULLISH_TREND":
                trend_dir_bonus = 8
                reasons.append({"text": "Bullish Trend Alignment", "type": "positive", "label": "TREND", "value": "BULLISH", "impact": 8})

            # MODULE 5 V6.3: MARKET STRUCTURE VALIDATION
            market_structure_state = structure.get("market_structure_state", "NEUTRAL_STRUCTURE")
            structure_penalty = 0
            if market_structure_state == "BEARISH_STRUCTURE":
                structure_penalty = -30
                reasons.append({"text": "Bearish Market Structure (LH/LL)", "type": "negative", "label": "STRUCTURE", "value": "BEARISH", "impact": -30})
            elif market_structure_state == "BULLISH_STRUCTURE":
                reasons.append({"text": "Bullish Market Structure (HH/HL)", "type": "positive", "label": "STRUCTURE", "value": "BULLISH", "impact": 0})

            # MODULE 1 V6.3: SECTOR MOMENTUM VALIDATION
            sector = market_service.get_sector_for_symbol(sym)
            sector_densities = global_index_ctx.get("sector_densities", {})
            sector_density = sector_densities.get(sector, 0.0)
            sector_strength = False
            sector_bonus = 0
            sector_penalty_v6_3 = 0
            
            if sector_density >= 0.40:
                sector_strength = True
                sector_bonus = 6
                reasons.append({"text": "High Sector Participation", "type": "positive", "label": "SECTOR", "value": f"{round(sector_density*100,0)}%", "impact": 6})
            elif sector_density < 0.15:
                # Isolated move, could be low institutional support
                sector_penalty_v6_3 = -10
                reasons.append({"text": "Low Sector Density", "type": "negative", "label": "SECTOR", "value": f"{round(sector_density*100,0)}%", "impact": -10})

            # MODULE 5 V6.1: VWAP RECLAIM BONUS
            vwap_reclaim_bonus = 0
            if len(df_15m) >= 3:
                vwap_series = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap_series(df_15m)
                # Cross above and hold for 2 candles (current & prev above, candle before that below)
                if (df_15m['close'].iloc[-1] > vwap_series.iloc[-1] and 
                    df_15m['close'].iloc[-2] > vwap_series.iloc[-2] and 
                    df_15m['close'].iloc[-3] < vwap_series.iloc[-3]):
                    
                    if rvol_val > 1.5:
                        vwap_reclaim_bonus = 15
                        reasons.append({"text": "Institutional VWAP Reclaim", "type": "positive", "label": "VWAP", "value": "RECLAIM", "impact": 15})
            
            rvol_bonus = 0
            if rvol_val > 2.5:
                rvol_bonus = 18
                reasons.append({"text": "Institutional RVOL Ignition", "type": "positive", "label": "RVOL", "value": f"{round(rvol_val,2)}x", "impact": 18})
            elif rvol_val > 1.5:
                rvol_bonus = 10
                reasons.append({"text": "Strong Relative Volume", "type": "positive", "label": "RVOL", "value": f"{round(rvol_val,2)}x", "impact": 10})

            # Phase 2: EMA Fan & Convergence Bonuses
            fan_bonus = ta_15m.get("fan_bonus", 0)
            
            # Market Context (Bonus/Malus applied later outside the 100% boundary)
            index_score = index_ctx.get("score", 50)
            
            # MODULE 2: RVOL & Liquidity Acceleration
            # Default state
            liquidity_acceleration_state = "NEUTRAL"
            acceleration_detected = False
            liq_accel_bonus = 0
            liq_accel_penalty = 0
            volume_candle_sequence = []
            
            if len(df_15m) >= 3:
                # FIX 1: Candle Definitions (Completed 15-minute candles only)
                v1 = float(df_15m['volume'].iloc[-3]) # Volume of candle -3 (completed)
                v2 = float(df_15m['volume'].iloc[-2]) # Volume of candle -2 (completed)
                v3 = float(df_15m['volume'].iloc[-1]) # Volume of candle -1 (completed)
                # Note: Currently forming candle is NEVER used.
                volume_candle_sequence = [v1, v2, v3]
                
                # Condition A: True Acceleration
                is_accel = v3 > v2 and v2 > v1 and v3 >= 1.2 * v2
                acceleration_detected = is_accel
                # FIX 2 (Patch 4): Deterministic Priority Mapping
                # 1. EXHAUSTION_WARNING (Highest Priority)
                if rvol_val >= 2.0 and v3 < v2:
                    liquidity_acceleration_state = "EXHAUSTION_WARNING"
                    liq_accel_penalty = -12
                    reasons.append({"text": "Institutional Exhaustion Alert", "type": "negative", "label": "VOL", "value": "EXHAUSTION", "impact": -12})
                # 2. ACCELERATION_CONFIRMED
                elif is_accel:
                    liquidity_acceleration_state = "ACCELERATION_CONFIRMED"
                    liq_accel_bonus = 6
                    reasons.append({"text": "Confirmed Liquidity Acceleration", "type": "positive", "label": "LIQUIDITY", "value": "ACCEL", "impact": 6})
                    
                    # Institutional Ignition (Additive +10 if RVOL >= 2.5)
                    if rvol_val >= 2.5:
                        liq_accel_bonus += 10
                        reasons.append({"text": "Strong Institutional Ignition", "type": "positive", "label": "IGNITION", "value": "STRONG", "impact": 10})
                # 3. NEUTRAL
                else:
                    liquidity_acceleration_state = "NEUTRAL"
                    if rvol_val > 1.5:
                        liq_accel_penalty = -8
                        reasons.append({"text": "Weak Volume Participation (Slow Start)", "type": "negative", "label": "LIQUIDITY", "value": "WEAK_SPIKE", "impact": -8})
                    
                pass # End of len(df_15m) >= 3 block

            # Institutional Bonus (Intraday Bias)
            inst_bonus = 0
            if rs_rating > 80: inst_bonus += 5 # Trade with Leaders
            if "Accumulation" in spon_action: inst_bonus += 2 # Buy Dips
            if "Distribution" in spon_action: inst_bonus -= 5 # Avoid Longs
            
            # --- DAY CHANGE CALCULATION (Crucial for Guardrails) ---
            day_change_pct = 0
            today_date = df_5m.index[-1].date()
            prev_days_df = df_5m[df_5m.index.date < today_date]
            if not prev_days_df.empty:
                prev_close = prev_days_df['close'].iloc[-1]
                day_change_pct = ((real_price - prev_close) / prev_close) * 100
            else:
                today_open = df_5m[df_5m.index.date == today_date]['open'].iloc[0]
                day_change_pct = ((real_price - today_open) / today_open) * 100
            
            # NEW: Volume Acceleration (Momentum Ignition)
            vol_acc_bonus = 0
            vol_acc_tag = ""
            try:
                v_last = df_5m['volume'].iloc[-1]
                v_prev = df_5m['volume'].iloc[-2]
                vol_acc = v_last / v_prev if v_prev > 0 else 0
                
                if vol_acc > 1.8:
                    vwap_val = ta_15m.get("vwap_val", 0)
                    if real_price > vwap_val:
                        if vol_acc > 2.5:
                            vol_acc_bonus = 18
                        else:
                            vol_acc_bonus = 12
                        
                        vol_acc_tag = " [🚀 MOMENTUM IGNITION]"
                        reasons.append({
                            "text": "Volume Acceleration",
                            "type": "positive",
                            "label": "IGNITION",
                            "value": f"{round(vol_acc, 2)}x Spike",
                            "impact": vol_acc_bonus
                        })
                        print(f"🚀 {sym} Momentum Ignition! Vol Acc: {vol_acc:.2f}x (+{vol_acc_bonus})")
            except:
                pass

            # Daily Momentum Guardrail (Refined V3.1)
            daily_momentum_bonus = 0
            if 1.0 <= day_change_pct < 2.0:
                daily_momentum_bonus = 5
            elif 2.0 <= day_change_pct < 4.0:
                daily_momentum_bonus = 10
            elif 4.0 <= day_change_pct < 6.0:
                daily_momentum_bonus = 5
            elif day_change_pct >= 6.0:
                daily_momentum_bonus = 0
                
            if day_change_pct > 8.0:
                daily_momentum_bonus = -20
                reasons.append({
                    "text": "Parabolic Exhaustion",
                    "type": "negative",
                    "label": "GUARD",
                    "value": f"{round(day_change_pct, 2)}% Up",
                    "impact": -20
                })
            
            # Note: dev_penalty (duplicate VWAP) removed as Fix 1
            sector = market_service.get_sector_for_symbol(sym)
            # Note: dev_penalty (duplicate VWAP) removed as Fix 1
            sector = market_service.get_sector_for_symbol(sym)
            sector_bonus = 0
            
            sector_perfs = index_ctx.get("sector_perfs", {})
            if sector in sector_perfs and sector != "General":
                sector_change = sector_perfs.get(sector, 0.0)
                nifty_change = index_ctx.get("day_change_pct", 0.0)
                sector_alpha = sector_change - nifty_change
                
                if sector_alpha > 0.5:
                    sector_bonus = 10
                    reasons.append({
                        "text": "Sector Outperforming",
                        "type": "positive",
                        "label": "SECTOR",
                        "value": f"{sector} (+{round(sector_alpha, 2)}%)",
                        "impact": 10
                    })
                elif sector_alpha < 0:
                    sector_bonus = -8
                    reasons.append({
                        "text": "Sector Underperforming",
                        "type": "negative",
                        "label": "SECTOR",
                        "value": f"{sector} ({round(sector_alpha, 2)}%)",
                        "impact": -8
                    })
            
            
            # Attach index_change to the stock's context state
            has_rs_leader_tag = (rs_alpha > 2.0 and index_change < -0.3)
            
            # --- Phase 1.5: Liquidity Pipeline Rejection ---
            # Calculate Average Daily Volume (ADV) from the 5-day OHLC data
            # df_15m has 15m bars. We extract dates to sum daily volumes, then average.
            liquidity_bonus = 0
            try:
                # 1. ADV Check (> 500k)
                # Resample back to daily to get true ADV
                daily_vols = df_15m['volume'].resample('1D').sum()
                daily_vols = daily_vols[daily_vols > 0] # Filter out weekends/holidays
                adv = daily_vols.mean() if not daily_vols.empty else 0
                
                # 2. Traded Value Check (> 10Cr by 10:30 AM)
                market_tz = pytz.timezone(settings.MARKET_TIMEZONE)
                now = datetime.now(market_tz)
                is_morning = (now.hour == 9) or (now.hour == 10 and now.minute <= 30)
                
                today = now.date()
                today_df = df_15m[df_15m.index.date == today]
                today_vol = today_df['volume'].sum() if not today_df.empty else 0
                traded_value_cr = (today_vol * real_price) / 10000000 # Convert to Crores
                
                liquidity_rejected = False
                rej_reason = ""
                
                if adv < 500000:
                    liquidity_rejected = True
                    rej_reason = f"Low ADV ({adv/100000:.1f}L < 5L)"
                elif is_morning and traded_value_cr < 10.0:
                    liquidity_rejected = True
                    rej_reason = f"Low Traded Value by 10:30 ({traded_value_cr:.1f}Cr < 10Cr)"
                    
                if liquidity_rejected:
                    liquidity_bonus = -50
                    reasons.append({
                        "text": "Liquidity Rejection",
                        "type": "negative",
                        "label": "LIQUIDITY",
                        "value": rej_reason,
                        "impact": -50
                    })
                    print(f"🚫 {sym} Rejected by Liquidity Filter: {rej_reason}")
            except Exception as e:
                print(f"Error in Liquidity Check for {sym}: {e}")
            
            # PHASE 5: V4 Market Regime Filter (Global Traffic Light)
            regime = index_ctx.get("market_regime", "Mixed")
            regime_adj = 0
            
            if regime == "Mixed":
                regime_adj = -5
                reasons.append({
                    "text": "Market Regime: Mixed",
                    "type": "negative",
                    "label": "REGIME",
                    "impact": -5
                })
            elif regime == "Sideways / Choppy":
                regime_adj = -10 # Module 6 V4: Increased to -10 direct score penalty
                reasons.append({
                    "text": "Market Regime: Sideways",
                    "type": "negative",
                    "label": "REGIME",
                    "impact": -10
                })
            elif regime == "Strong Bullish":
                reasons.append({
                    "text": "Market Regime: Strong Bullish",
                    "type": "positive",
                    "label": "REGIME",
                    "impact": 0
                })
            elif regime == "Strong Bearish":
                reasons.append({
                    "text": "Market Regime: Strong Bearish",
                    "type": "negative",
                    "label": "REGIME",
                    "impact": 0
                })
                    
            # Market Breadth (A/D Ratio Momentum Bonus)
            ad_ratio = index_ctx.get("ad_ratio", 1.0)
            ad_bonus = 0
            if ad_ratio > 1.5:
                ad_bonus = 5
            elif ad_ratio < 0.8:
                ad_bonus = -5
            
            # Advanced VWAP Scenarios
            vwap_ctx = ta_15m.get("vwap_ctx", {})
            vwap_bonus = 0
            
            if vwap_ctx.get("price_above") and vwap_ctx.get("slope_up"):
                vwap_bonus += 10
                reasons.append({
                    "text": "Bullish VWAP Trajectory",
                    "type": "positive",
                    "label": "VWAP",
                    "value": "Price > VWAP & Rising Slope",
                    "impact": 10
                })
            
            if vwap_ctx.get("reclaim"):
                vwap_bonus += 15
                reasons.append({
                    "text": "Institutional VWAP Reclaim",
                    "type": "positive",
                    "label": "RECLAIM",
                    "value": "High Volume VWAP Cross",
                    "impact": 15
                })
                
            if vwap_ctx.get("oscillating"):
                vwap_bonus += 2
                reasons.append({
                    "text": "VWAP Magnet Zone",
                    "type": "neutral",
                    "label": "VWAP",
                    "value": "Oscillating Around Anchor",
                    "impact": 2
                })

            # --- PHASE 4: INSTITUTIONAL SMART MONEY ACCUMULATION (V3.4) ---
            accumulation_bonus = 0
            if acc["accumulation_detected"]:
                # Upgrade 2 V4.2: Strengthened Breakout Confirmation
                v_last = df_5m['volume'].iloc[-1]
                v_avg_cons = acc.get("avg_vol_consolidation", 0)
                
                is_strong_breakout = (
                    acc["is_breakout"] and 
                    rvol_val >= 1.8 and 
                    v_last > v_avg_cons
                )
                
                if is_strong_breakout:
                    accumulation_bonus = 28 # +18 for accumulation + 10 for strong breakout
                    reasons.append({
                        "text": "Institutional Accumulation Breakout",
                        "type": "positive",
                        "label": "SMART",
                        "value": "Breakout confirmed (Vol/RVOL)",
                        "impact": 28
                    })
                    setup_tag += " [🏦 Smart Money Accumulation]"
                else:
                    accumulation_bonus = 18
                    reasons.append({
                        "text": "Smart Money Accumulation",
                        "type": "positive",
                        "label": "SMART",
                        "value": "Consolidation + Vol Accumulation",
                        "impact": 18
                    })
                    setup_tag += " [🏦 Smart Money Accumulation]"
            
            # Risk control / Invalidation
            if acc["is_breakdown"]:
                accumulation_bonus = -15
                reasons.append({
                    "text": "Accumulation Invalidation (Breakdown)",
                    "type": "negative",
                    "label": "GUARD",
                    "value": "Break Below Consolidation Low",
                    "impact": -15
                })

            # Initialize all new bonus/penalty variables to 0
            pullback_bonus = 0
            sweep_bonus = 0
            reclaim_bonus = 0
            squeeze_bonus = 0
            gap_bonus = 0
            poc_bonus = 0
            fan_bonus = 0
            rvol_bonus = 0 # This might be `rvol_val` related, need to check usage
            inst_bonus = 0 # This is already used for `inst_bonus`
            mtf_bonus = 0
            acc_bonus = 0 # This is already `accumulation_bonus`
            institutional_volume_bonus = 0
            trend_bonus = 0
            vwap_reclaim_bonus = 0
            trend_dir_bonus = 0
            sector_bonus = 0 # This is already `sector_bonus`
            liq_accel_bonus = 0
            vol_acc_bonus = 0 # This is already `vol_acc_bonus`

            exhaustion_penalty = 0
            context_penalty = 0
            overheat_penalty = 0
            chop_penalty = 0
            volume_penalty = 0
            structure_penalty = 0
            fake_breakout_penalty = 0
            vwap_ext_penalty = 0
            trend_penalty = 0
            trap_penalty = 0
            trend_dir_penalty = 0
            sector_penalty_v6_3 = 0
            liq_accel_penalty = 0
            mtf_penalty = 0

            # --- PHASE 4: Pattern Analysis Blocks (Modules 3, 4, 14) ---
            
            # Module 4: Smart Money Accumulation
            if acc["accumulation_detected"]:
                if acc["is_breakout"] and rvol_val >= 1.8:
                    accumulation_bonus = 28
                    reasons.append({"text": "Institutional Accumulation Breakout", "type": "positive", "label": "SMART", "value": "Breakout confirmed", "impact": 28})
                else:
                    accumulation_bonus = 18
                    reasons.append({"text": "Smart Money Accumulation", "type": "positive", "label": "SMART", "value": "Consolidation", "impact": 18})
            if acc["is_breakdown"]:
                accumulation_bonus = -15
                reasons.append({"text": "Accumulation Invalidation", "type": "negative", "label": "GUARD", "value": "Breakdown", "impact": -15})
            
            # Module 3: Liquidity Sweep & Stop Hunt
            candle_hold_count = sweep.get("candle_hold_count", 0)
            if candle_hold_count >= 3:
                reclaim_bonus = 6
                reasons.append({"text": "Breakout Continuation Hold", "type": "positive", "label": "SMART", "value": f"{candle_hold_count} Bars", "impact": 6})
            
            # Module 14 Extension: Institutional Trap Reclaim
            trap_data = ta_15m.get("trap", {})
            if trap_data.get("is_trap"):
                sweep_bonus += 15
                reasons.append({"text": "Institutional Trap Reclaim", "type": "positive", "label": "TRAP", "value": "RECLAIM", "impact": 15})
            
            # Module 2 Extension: Volume Ignition
            try:
                v_last = df_5m['volume'].iloc[-1]
                v_prev = df_5m['volume'].iloc[-2]
                vol_acc_ratio = v_last / v_prev if v_prev > 0 else 0
                if vol_acc_ratio > 1.8 and real_price > vwap_val:
                    vol_acc_bonus = 18 if vol_acc_ratio > 2.5 else 12
                    reasons.append({"text": "Volume Acceleration Ignition", "type": "positive", "label": "IGNITION", "value": f"{round(vol_acc_ratio,1)}x", "impact": vol_acc_bonus})
            except: pass

            # --- PHASE 5: Additional Patterns (Pullbacks, Fans, ADX Extreme) ---
            pullback = ta_15m.get("pullback", {"is_pullback": False})
            if pullback["is_pullback"]:
                pullback_bonus = 25
                reasons.append({"text": "Bullish Pullback Entry", "type": "positive", "label": "SETUP", "value": pullback.get("type", "VWAP"), "impact": 25})
            
            fan_bonus = ta_15m.get("fan_bonus", 0)
            if adx_val > 25: # Standardized to V6.3 Master Spec
                trend_bonus += 10
                reasons.append({"text": "Confirmed Trend Momentum", "type": "positive", "label": "ADX", "value": f"{round(adx_val,1)}", "impact": 10})
            

            # Time of Day Bias
            now_time = now_timing.time()

            # Market Alpha & Regime (Module 6)
            index_change = index_ctx.get("day_change_pct", 0.0)
            
            regime = index_ctx.get("market_regime", "Mixed")
            if regime == "Mixed": regime_adj = -5
            elif regime == "Sideways / Choppy": regime_adj = -10
            
            # --- PHASE 6: V6.3 STANDARDIZED EXECUTION FLOW ---
            
            # FIX 3 (Patch 4): Institutional Momentum Cap Rule
            # Triggers: Liquidity Accel, Institutional Ignition, VWAP Reclaim, ADX Trend
            is_institutional_ignition = rvol_val >= 2.5
            if (liquidity_acceleration_state == "ACCELERATION_CONFIRMED" and 
                is_institutional_ignition and 
                vwap_reclaim_bonus > 0 and 
                trend_bonus > 0):
                
                inst_mom_total = liq_accel_bonus + rvol_bonus + vwap_reclaim_bonus + trend_bonus
                if inst_mom_total > 45:
                    scale = 45.0 / inst_mom_total
                    liq_accel_bonus *= scale
                    rvol_bonus *= scale
                    vwap_reclaim_bonus *= scale
                    trend_bonus *= scale
                    reasons.append({
                        "text": "Institutional Momentum Cap Applied",
                        "type": "neutral",
                        "label": "GUARD",
                        "value": f"{round(inst_mom_total,1)} -> 45.0",
                        "impact": 0
                    })
            
            # 1. MODULES 1–8: CONSOLIDATED SCORING SUMMARY
            m1_8_bonus_total = (
                pullback_bonus + reclaim_bonus + sweep_bonus + 
                squeeze_bonus + gap_bonus + poc_bonus + fan_bonus + 
                rvol_bonus + inst_bonus + mtf_bonus + acc_bonus + 
                institutional_volume_bonus + trend_bonus + vwap_reclaim_bonus + 
                trend_dir_bonus + sector_bonus + liq_accel_bonus + 
                vol_acc_bonus + accumulation_bonus + daily_momentum_bonus +
                ad_bonus + vwap_bonus
            )
            
            m1_8_penalty_total = (
                exhaustion_penalty + context_penalty + 
                overheat_penalty + chop_penalty + volume_penalty + 
                structure_penalty + fake_breakout_penalty + 
                vwap_ext_penalty + trend_penalty + trap_penalty + 
                trend_dir_penalty + sector_penalty_v6_3 + abs(liq_accel_penalty) + 
                regime_adj + mtf_penalty + liquidity_bonus
            )
            
            # Base Scoring Weights (Module 8)
            base_score_weighted = (vwap_score*0.30) + (adx_score*0.25) + (pa_score*0.25) + (volume_expansion_ratio*10*0.20)
            
            # Final Score Pre-Timing
            final_score_pre_timing = base_score_weighted + m1_8_bonus_total + m1_8_penalty_total
            final_score_pre_timing = max(0, min(160, final_score_pre_timing))
            
            # 2. VOLUME GUARD CHECK & TIMING BONUS
            if volume_validation_state == "LOW_VOLUME_BLOCK" and final_score_pre_timing >= 78:
                is_volume_block = True
            
            scan_window = self._is_optimal_window(now_timing)
            timing_bonus = 3 if (scan_window == "OPTIMAL" and final_score_pre_timing >= 70) else 0
            
            final_score = final_score_pre_timing + timing_bonus
            final_score = round(max(0, min(160, final_score)), 1)
            
            # 4. SIGNAL CLASSIFICATION (Module 9)
            if final_score >= 105: signal_type = "PIONEER PRIME 🏆"
            elif final_score >= 92: signal_type = "HIGH CONVICTION BUY 👑"
            elif final_score >= 78: signal_type = "BUY SETUP ✅"
            elif final_score >= 67: signal_type = "WATCHLIST ⚖"
            else: signal_type = "IGNORE 🚫"

            # 5-6. KILL-SWITCHES & FINAL ELIGIBILITY
            block_trade = False
            block_reason = None
            
            if vwap_deviation_pct > 4.0: block_trade, block_reason = True, "Critical VWAP Extension"
            elif sweep.get("fake_breakout_flag"): block_trade, block_reason = True, "Failed Breakout Collapse"
            elif adx_val < 18: block_trade, block_reason = True, "Weak ADX Momentum"
            elif trend_direction_state == "BEARISH_TREND": block_trade, block_reason = True, "Bearish Trend Guard"
            elif market_structure_state == "BEARISH_STRUCTURE": block_trade, block_reason = True, "Bearish Structure"
            elif is_volume_block: block_trade, block_reason = True, "Volume Validation Block"
            elif trap_move_detected: block_trade, block_reason = True, "Institutional Trap"
            elif regime == "Strong Bearish": block_trade, block_reason = True, "Market Regime: Strong Bearish"
            
            if block_trade:
                signal_type = "IGNORE 🚫"
                confidence_label = block_reason
            else:
                confidence_label = f"{round(final_score/1.6,1)}% Probability"

            # Meta Calculation for Return
            target_val = ta_15m.get("resistance", real_price * 1.02)
            stop_val = ta_15m.get("support", real_price * 0.99)
            
            # Setup Tags
            setup_tag = ""
            if "PRIME" in signal_type: setup_tag += " [💎 PRIME]"
            if mtf_ctx.get("is_bullish"): setup_tag += " [🌀 1H ALIGN]"

            return {
                "symbol": sym,
                "price": real_price,
                "score": final_score,
                "signal_type": signal_type,
                "verdict": f"{signal_type} ({confidence_label})",
                "setup_tag": setup_tag,
                "reasons": reasons[:8],
                "target": round(target_val, 2),
                "stop_loss": round(stop_val, 2),
                "rvol": round(rvol_val, 2),
                "adv20": round(adv20, 0),
                "vwap_deviation": round(vwap_deviation_pct, 2),
                "market_regime": regime,
                "trend_state": trend_direction_state,
                "alpha_intel": {
                    "growth_probability": confidence_label,
                    "risk_level": "Low" if final_score > 90 else "High" if final_score < 60 else "Medium",
                    "confidence": f"{round(final_score/1.6,1)}%"
                },
                "pioneer_prime_flag": "PRIME" in signal_type,
                "volume_expansion_ratio": round(volume_expansion_ratio, 2),
                "institutional_volume_flag": institutional_volume_flag,
                "scan_window": scan_window,
                # FIX 3 (Patch 2): Structured Metadata
                "liquidity_acceleration_state": liquidity_acceleration_state,
                "market_structure": market_structure_state,
                "trap_range_expansion": ta_15m.get("trap_range_expansion", False),
                "sector_density_pct": round(sector_density * 100, 2)
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Intraday Engine failed for {sym}: {e}")
            return None

    async def run_scan(self, job_id: str):
        """
        Main entry point for an Intraday Job.
        Processes a selection of symbols for real-time advice with robust sync.
        """
        from app.services.market_discovery import market_discovery
        
        # 1. Get Symbols (Full Market)
        symbols = await market_discovery.get_full_market_list()
        
        # Fallback to static if discovery fails
        if not symbols:
            symbols = list(market_service.stock_master)
            
        total = len(symbols)
        print(f"Intraday Engine: Starting Scan for Job {job_id} with {total} symbols")
        
        # Pre-fetch Global Index Context
        global_index_ctx = await self._get_index_context()

        # 2. Initialize Per-Job State (Avoid Instance Collisions)
        self.job_states[job_id] = {
            "results": [],
            "failed_symbols": [],
            "active": [],
            "progress": 0,
            "is_running": True,
            "stop_requested": False,
            "pause_requested": False,
            "last_data_sync": 0 # Track progress of last data sync
        }

        # 3. Start Decoupled Progress Sync Loop
        self.job_states[job_id]["main_task"] = asyncio.current_task()
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        try:
            # 4. Iterate with Semaphore
            async def sem_task(sym, idx):
                # Global Stop Check (Memory Based - Instant)
                if self.job_states[job_id].get("stop_requested"): return

                # PAUSE CHECK: Spin wait if paused (Before entering semaphore)
                while self.job_states[job_id].get("pause_requested"):
                    if self.job_states[job_id].get("stop_requested"): return
                    try: 
                        await asyncio.sleep(1)
                    except asyncio.CancelledError:
                        return 

                try:
                    async with self.semaphore:
                        # Double Check inside semaphore
                        if self.job_states[job_id].get("stop_requested"): return

                        # Small delay to prevent API hammering/blocks
                        await asyncio.sleep(0.1)

                        # Defensive: Extract symbol string if discovery gave us objects
                        symbol_str = sym["symbol"] if isinstance(sym, dict) else sym

                        state = self.job_states[job_id]
                        state["active"].append(symbol_str)
                        print(f"[{idx+1}/{total}] [INT] Analyzing: {symbol_str}", flush=True)
                        try:
                            # PASS GLOBAL INDEX CONTEXT
                            res = await self.analyze_stock(symbol_str, job_id, global_index_ctx)
                            if res:
                                state["results"].append(res)
                            else:
                                state["failed_symbols"].append({"symbol": symbol_str, "reason": "No data / Skipped"})
                        except Exception as e:
                            # print(f"Intraday Scan Error for {symbol_str}: {e}")
                            state["failed_symbols"].append({"symbol": symbol_str, "reason": str(e)})
                        finally:
                            state["progress"] += 1
                            if symbol_str in state["active"]:
                                state["active"].remove(symbol_str)
                except asyncio.CancelledError:
                    return

            tasks = [sem_task(s, i) for i, s in enumerate(symbols)]
            await asyncio.gather(*tasks)
            
        except asyncio.CancelledError:
            print(f"🛑 Intraday Job {job_id} CANCELLED via Task Cancellation")
            
        finally:
            # SIGNAL LOOP TO STOP
            if job_id in self.job_states:
                self.job_states[job_id]["is_running"] = False
            
            # Wait for it to finish gracefully
            await sync_task

        # 6. Final Output: Professional Ranking (Senior Specialist Standard)
        state = self.job_states.get(job_id, {"results": [], "failed_symbols": []})
        
        def ranking_key(x):
            tags = x.get("setup_tag", "")
            base_score = x.get("score", 0)
            
            # Tier 1: Ultra High Conviction Symbols (Diamonds/Traps)
            conviction_weight = 0
            if "👑" in tags: conviction_weight += 100 # Top Priority: Pioneer Prime
            if "💎" in tags: conviction_weight += 60 # Priority to RECLAIMS and SQUEEZES
            if "🌀" in tags: conviction_weight += 30
            if "⚖️" in tags: conviction_weight += 20
            if "📈 BULLISH DIV" in tags: conviction_weight += 20
            
            return (conviction_weight + base_score)

        final_results = sorted(state["results"], key=ranking_key, reverse=True)
        final_payload = {
            "total_scanned": total,
            "progress": total,
            "total_steps": total,
            "success_count": len(final_results),
            "data": final_results,
            "failed_symbols": state.get("failed_symbols", []),
            "status_msg": "Completed"
        }
        # Cleanup state memory
        if job_id in self.job_states: del self.job_states[job_id]
        
        return sanitize_data(final_payload) 

    async def _progress_loop(self, job_id: str, total: int):
        """Background pulse for DB sync."""
        from sqlalchemy.orm.attributes import flag_modified
 
        print(f"📡 Intraday Progress Sync started for {job_id}")
        while job_id in self.job_states and self.job_states[job_id].get("is_running"):
            try:
                state = self.job_states.get(job_id)
                if not state: break
                
                # Check Pause for Sync Loop (Optional: Update status message)
                status_suffix = ""
                if state.get("pause_requested"):
                    status_suffix = " [PAUSED]"

                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    current_result = {} # Initialize for safety/No NameError
                    if job_obj:
                        current_result = job_obj.result or {}
                        if not isinstance(current_result, dict): current_result = {}
                        
                        active_str = ", ".join(state["active"][:3])
                        current_result["progress"] = state["progress"]
                        current_result["total_steps"] = total
                        current_result["active_symbols"] = list(state["active"])
                        current_result["status_msg"] = f"Analyzing: {active_str}{status_suffix}"
                        
                        # Partial Data Sync: Sync results every 5 stocks for live UI updates
                        current_count = len(state.get("results", []))
                        last_sync = state.get("last_data_sync", 0)
                        if current_count - last_sync >= 5 or current_count == total:
                            current_result["data"] = list(state["results"])
                            current_result["failed_symbols"] = list(state.get("failed_symbols", []))
                            # Pre-calculate sectors for O(1) API fetches (Fast Toggles)
                            current_result["sectors"] = self._group_by_sector(current_result["data"])
                            state["last_data_sync"] = current_count
                            # print(f"📊 [INTRADAY-SYNC] Partial Data Sync: {current_count} results")

                        job_obj.result = sanitize_data(current_result)
                        flag_modified(job_obj, "result")
                        job_obj.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception as e:
                print(f"Intraday Sync Warning: {e}")
            await asyncio.sleep(2.0)
        print(f"📡 Intraday Progress Sync stopped for {job_id}")

    async def stop_job(self, job_id: str):
        """
        Instant Stop Signal.
        """
        if job_id in self.job_states:
            print(f"🛑 STOPPING Intraday Job {job_id}...")
            self.job_states[job_id]["stop_requested"] = True
            self.job_states[job_id]["is_running"] = False
            
            # Cancel the Main Task if stored
            main_task = self.job_states[job_id].get("main_task")
            if main_task:
                print(f"🛑 Cancelling Main Task for Job {job_id}")
                main_task.cancel()

    async def pause_job(self, job_id: str):
        """
        Pause Signal.
        """
        if job_id in self.job_states:
            print(f"⏸️ PAUSING Intraday Job {job_id}...")
            self.job_states[job_id]["pause_requested"] = True

    async def resume_job(self, job_id: str):
        """
        Resume Signal.
        """
        if job_id in self.job_states:
            print(f"▶️ RESUMING Intraday Job {job_id}...")
            self.job_states[job_id]["pause_requested"] = False

intraday_engine = IntradayEngine()
