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
        reasons = [] # INITIALIZE UNIVERSAL REASONS LIST
        setup_tag = "" # INITIALIZE TAGS FOR SCORING ALIGNMENT
        block_trade = False
        block_reason = ""
        
        # --- SCORING INITIALIZATION ---
        pullback_bonus = reclaim_bonus = sweep_bonus = squeeze_bonus = 0
        gap_bonus = poc_bonus = fan_bonus = rvol_bonus = 0
        inst_bonus = mtf_bonus = acc_bonus = accumulation_bonus = 0
        institutional_volume_bonus = trend_bonus = vwap_reclaim_bonus = 0
        trend_dir_bonus = sector_bonus = daily_momentum_bonus = 0
        regime_bonus = ad_bonus = liquidity_bonus = 0
        vwap_bonus = vol_acc_bonus = 0
        liq_accel_bonus = liq_accel_penalty = 0
        mtf_penalty = 0
        regime_adj = 0
        breadth_bonus = breadth_penalty = 0
        volume_validation_state = "PASSED"
        is_volume_block = False
        
        exhaustion_penalty = dev_penalty = context_penalty = 0
        overheat_penalty = chop_penalty = volume_penalty = 0
        structure_penalty = fake_breakout_penalty = vwap_ext_penalty = 0
        # V6.3 Sequential Refactor
        trend_penalty = trap_penalty = trend_dir_penalty = 0
        sector_penalty_v6_3 = 0
        block_trade = False
        block_reason = ""
        
        # V6.3+ Institutional Flow Metrics
        delivery_ratio = None
        volume_zscore = 0
        avg_range_10 = 0
        candle_range = 0
        
        # V6.3+ Technical & Scoring Metrics
        volatility_bonus = 0
        float_rotation_bonus = 0
        atr_5 = atr_20 = 0
        atr_ratio = 1.0
        free_float = 0

        try:
            # CHECK STOP 1
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

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
            task_5m = market_service.get_ohlc(sym, period="3d", interval="5m", fast_fail=fast_fail)
            task_1h = market_service.get_ohlc(sym, period="7d", interval="1h", fast_fail=fast_fail)
            df_5m, df_1h = await asyncio.gather(task_5m, task_1h)
            
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
            
            # Technical Indicators
            ta_15m = ta_intraday.IntradayTechnicalAnalysis.analyze_stock(df_15m)
            sweep = ta_intraday.IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df_15m)
            acc = ta_intraday.IntradayTechnicalAnalysis.detect_smart_money_accumulation(df_15m)
            structure = ta_intraday.IntradayTechnicalAnalysis.detect_market_structure(df_15m)
            trap = ta_intraday.IntradayTechnicalAnalysis.detect_liquidity_trap(df_15m)
            trend_guard = ta_intraday.IntradayTechnicalAnalysis.detect_trend_direction(df_15m)
            if not ta_15m: return None
            
            ta_5m = await asyncio.to_thread(ta_intraday.IntradayTechnicalAnalysis.analyze_stock, df_5m)
            
            mtf_ctx = {"is_bullish": False, "reason": "No 1H Data"}
            if df_1h is not None and not df_1h.empty:
                ta_1h = await asyncio.to_thread(ta_intraday.IntradayTechnicalAnalysis.analyze_stock, df_1h)
                mtf_ctx = {
                    "is_bullish": ta_1h.get("is_bullish_trend", False),
                    "score": ta_1h.get("vwap_score", 50),
                    "trend": ta_1h.get("trend", "NEUTRAL")
                }
            
            # Initial Metrics
            vwap_score = ta_15m.get("vwap_score", 50)
            pa_score = ta_15m.get("pa_score", 50)
            adx_score = ta_15m.get("adx_score", 50)
            rvol_val = ta_15m.get("rvol_val", 1.0)
            adv20 = ta_15m.get("adv20", 0)
            vwap_val = ta_15m.get("vwap_val", real_price)
            vwap_deviation_pct = abs(real_price - vwap_val) / vwap_val * 100 if vwap_val > 0 else 0
            
            # --- STABILITY PATCH: SAFE METRIC EXTRACTION ---
            # Extract metrics from technical objects defensively
            adx_val = ta_15m.get("adx_details", {}).get("adx", 0)
            adx_slope = ta_15m.get("adx_details", {}).get("adx_slope", 0)
            adx_is_rising = ta_15m.get("adx_details", {}).get("is_rising", False)
            
            trap_move_detected = trap.get("trap_move_detected", False)
            trend_direction_state = trend_guard.get("trend_direction_state", "NEUTRAL_TREND")
            market_structure_state = structure.get("market_structure_state", "NEUTRAL_STRUCTURE")
            # --- END STABILITY PATCH ---
            
            # --- INSTITUTIONAL FLOW METRIC CALCULATIONS ---
            if len(df_15m) >= 10:
                v_series = df_15m['volume'].iloc[-20:] # 20 period window for Z-Score
                if v_series.std() > 0:
                    volume_zscore = (df_15m['volume'].iloc[-1] - v_series.mean()) / v_series.std()
                
                ranges = (df_15m['high'] - df_15m['low']).iloc[-10:]
                avg_range_10 = ranges.mean()
                candle_range = df_15m['high'].iloc[-1] - df_15m['low'].iloc[-1]
            
            delivery_ratio = index_ctx.get("delivery_ratio") # Expected optional input
            
            # --- VOLATILITY & FLOAT METRICS ---
            fund_data = await market_service.get_fundamentals(sym)
            free_float = fund_data.get("floatShares", fund_data.get("marketCap", 0) * 0.4 / real_price) # Fallback to 40% MCAP if unknown
            
            if len(df_15m) >= 20:
                atr_20_series = ta_intraday.AverageTrueRange(high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], window=20).average_true_range()
                atr_5_series = ta_intraday.AverageTrueRange(high=df_15m['high'], low=df_15m['low'], close=df_15m['close'], window=5).average_true_range()
                atr_20 = float(atr_20_series.iloc[-1])
                atr_5 = float(atr_5_series.iloc[-1])
                atr_ratio = atr_5 / max(atr_20, 0.0001)

            regime = index_ctx.get("market_regime", "Mixed")
            # --- PHASE 0: Pre-Scoring Metrics & Standard Guards ---
            # Module 12: VWAP Deviation Guard (Hard Block)
            if vwap_deviation_pct > 4.0: block_trade, block_reason = True, "Critical VWAP Extension"
            
            # Enhancement: ATR-Adjusted Deviation Guard
            if atr_20 > 0:
                vwap_atr_ratio = abs(real_price - vwap_val) / atr_20
                if vwap_atr_ratio > 2.5:
                    block_trade, block_reason = True, "Excessive VWAP Extension"
            
            # Module 13: ADX Filter (Hard Block)
            if adx_val < 18: block_trade, block_reason = True, "Weak ADX Momentum"
            
            # Module 6: Market Regime (Hard Block)
            if regime == "Strong Bearish": block_trade, block_reason = True, "Market Regime: Strong Bearish"

            # Module 14: Liquidity Trap Detector (Hard Block)
            if trap_move_detected: block_trade, block_reason = True, "Institutional Trap"
            
            # Enhancement: VWAP Reclaim Failure Trap
            if len(df_15m) >= 3:
                vwap_series = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap_series(df_15m)
                # Price broke above but fell back below within 2 candles with decreasing volume
                p1, p2, p3 = df_15m['close'].iloc[-3], df_15m['close'].iloc[-2], df_15m['close'].iloc[-1]
                v1, v2, v3 = df_15m['volume'].iloc[-3], df_15m['volume'].iloc[-2], df_15m['volume'].iloc[-1]
                vwap1, vwap2, vwap3 = vwap_series.iloc[-3], vwap_series.iloc[-2], vwap_series.iloc[-1]
                
                # Check if p2 broke above vwap but p3 fell below, and v3 < v2
                if p2 > vwap2 and p3 < vwap3 and v3 < v2:
                    block_trade, block_reason = True, "VWAP Reclaim Trap"

            # Module 5.1: Trend Direction Guard (Hard Block)
            if trend_direction_state == "BEARISH_TREND": block_trade, block_reason = True, "Bearish Trend Guard"
            
            # Module 5.3: Market Structure Guard (Hard Block)
            if market_structure_state == "BEARISH_STRUCTURE": block_trade, block_reason = True, "Bearish Structure"

            # Module 3: Sweep Fake Breakout (Hard Block)
            if sweep.get("fake_breakout_flag"): block_trade, block_reason = True, "Failed Breakout Collapse"

            # --- PHASE 1: Modular Scoring Logic ---
            
            # Module 1: Sector Participation
            sector = market_service.get_sector_for_symbol(sym)
            sector_densities = index_ctx.get("sector_densities", {})
            sector_density = sector_densities.get(sector, 0.0)
            
            # Enhancement: Time-Weighted Sector Density
            t = now_timing.hour * 100 + now_timing.minute
            time_factor = 1.0 # Default fallback
            if 915 <= t <= 930: time_factor = 0.6
            elif 930 < t <= 1030: time_factor = 1.0
            elif t > 1030: time_factor = 1.2
            
            sector_density_weighted = sector_density * time_factor
            
            if sector_density_weighted >= 0.40:
                sector_bonus = 6
                reasons.append({"text": "High Sector Participation", "type": "positive", "label": "SECTOR", "value": f"{round(sector_density_weighted*100,0)}%", "impact": 6})
            elif sector_density_weighted < 0.15:
                sector_penalty_v6_3 = -10
                reasons.append({"text": "Low Sector Density", "type": "negative", "label": "SECTOR", "value": f"{round(sector_density_weighted*100,0)}%", "impact": -10})

            # Module 11: Sector Alpha (Outperformance)
            sector_perfs = index_ctx.get("sector_perfs", {})
            if sector in sector_perfs and sector != "General":
                sector_change = sector_perfs.get(sector, 0.0)
                nifty_change = index_ctx.get("day_change_pct", 0.0)
                sector_alpha = sector_change - nifty_change
                
                # Smoothing protection for flat index
                if abs(nifty_change) < 0.2:
                    sector_alpha = sector_alpha * 0.5
                
                if sector_alpha > 0.5:
                    sector_bonus += 10
                    reasons.append({"text": "Sector Outperforming", "type": "positive", "label": "SECTOR", "value": f"{sector} (+{round(sector_alpha, 2)}%)", "impact": 10})
                elif sector_alpha < 0:
                    sector_bonus -= 8
                    reasons.append({"text": "Sector Underperforming", "type": "negative", "label": "SECTOR", "value": f"{sector} ({round(sector_alpha, 2)}%)", "impact": -8})

            # Module 12: Daily Momentum Guardrails
            today_date = df_5m.index[-1].date()
            prev_days_df = df_5m[df_5m.index.date < today_date]
            if not prev_days_df.empty:
                prev_close = prev_days_df['close'].iloc[-1]
                day_change_pct = ((real_price - prev_close) / prev_close) * 100
            else:
                today_open = df_5m[df_5m.index.date == today_date]['open'].iloc[0]
                day_change_pct = ((real_price - today_open) / today_open) * 100
                
            if 1.0 <= day_change_pct < 2.0: daily_momentum_bonus = 5
            elif 2.0 <= day_change_pct < 4.0: daily_momentum_bonus = 10
            elif 4.0 <= day_change_pct < 6.0: daily_momentum_bonus = 5
            elif day_change_pct >= 8.0:
                daily_momentum_bonus = -20
                reasons.append({"text": "Parabolic Exhaustion", "type": "negative", "label": "GUARD", "value": f"{round(day_change_pct, 2)}% Up", "impact": -20})

            # Module 6: Market Regime Adjustment
            if regime == "Mixed": regime_adj = -5
            elif regime == "Sideways / Choppy": regime_adj = -10
            
            # Optional Breadth Filter
            adv = index_ctx.get("advancing_stocks")
            dec = index_ctx.get("declining_stocks")
            if adv is not None and dec is not None:
                breadth_ratio = adv / max(dec, 1)
                if breadth_ratio > 1.2: breadth_bonus = 4
                elif breadth_ratio < 0.8: breadth_penalty = -5
                if breadth_bonus != 0 or breadth_penalty != 0:
                    reasons.append({"text": "Market Breadth Signal", "type": "positive" if breadth_ratio > 1.2 else "negative", "label": "BREADTH", "value": f"{round(breadth_ratio,2)}x", "impact": breadth_bonus + breadth_penalty})

            # Module 2: Liquidity Acceleration
            liquidity_acceleration_state = "NEUTRAL"
            if len(df_15m) >= 3:
                v1, v2, v3 = float(df_15m['volume'].iloc[-3]), float(df_15m['volume'].iloc[-2]), float(df_15m['volume'].iloc[-1])
                if rvol_val >= 2.0 and v3 < v2:
                    liquidity_acceleration_state = "EXHAUSTION_WARNING"
                    liq_accel_penalty = -12
                elif v3 > v2 and v2 > v1 and v3 >= 1.2 * v2:
                    liquidity_acceleration_state = "ACCELERATION_CONFIRMED"
                    liq_accel_bonus = 6
                    if rvol_val >= 2.5: liq_accel_bonus += 10
                elif rvol_val > 1.5:
                    liq_accel_penalty = -8
                
                # Enhancement: Spike Collapse Warning
                if v3 < v2 and v2 > v1 * 1.5:
                    liq_accel_penalty += -6
                    reasons.append({"text": "Volume Spike Collapse", "type": "negative", "label": "VOL", "impact": -6})
            
            # Module 4: Smart Money Accumulation
            if acc["accumulation_detected"]:
                accumulation_bonus = 28 if (acc["is_breakout"] and rvol_val >= 1.8) else 18
                reasons.append({"text": "Institutional Accumulation", "type": "positive", "label": "SMART", "impact": accumulation_bonus})
            if acc["is_breakdown"]: accumulation_bonus = -15
            
            # Enhancement: Narrow Range Accumulation Detection
            if volume_zscore > 2 and avg_range_10 > 0 and candle_range < (avg_range_10 * 0.6):
                accumulation_bonus += 6
                reasons.append({"text": "Narrow Range Accumulation", "type": "positive", "label": "SMART", "value": f"Z:{round(volume_zscore,1)}", "impact": 6})

            # Module 5.2 & 10: VWAP Reclaim Logic
            if len(df_15m) >= 3:
                vwap_series = ta_intraday.IntradayTechnicalAnalysis.calculate_vwap_series(df_15m)
                if df_15m['close'].iloc[-1] > vwap_series.iloc[-1] and df_15m['close'].iloc[-2] > vwap_series.iloc[-2] and df_15m['close'].iloc[-3] < vwap_series.iloc[-3]:
                    if rvol_val > 1.5: vwap_reclaim_bonus = 15

            vwap_ctx = ta_15m.get("vwap_ctx", {})
            if vwap_ctx.get("price_above") and vwap_ctx.get("slope_up"): vwap_bonus += 10
            if vwap_ctx.get("reclaim"): vwap_bonus += 15

            # Module 7: RVOL Institutional Ignition
            if rvol_val > 2.5: rvol_bonus = 18
            elif rvol_val > 1.5: rvol_bonus = 10
            
            # Enhancement: Delivery Confirmation
            if rvol_val > 2.0 and delivery_ratio and delivery_ratio > 55:
                rvol_bonus += 6
                reasons.append({"text": "Institutional Delivery Confirmed", "type": "positive", "label": "VOL", "value": f"{delivery_ratio}%", "impact": 6})
            
            # Enhancement: Float Rotation Signal
            float_rotation = df_15m['volume'].iloc[-1] / max(free_float, 1)
            if float_rotation > 0.08:
                float_rotation_bonus = 12
                reasons.append({"text": "Institutional Float Rotation", "type": "positive", "label": "FLOAT", "value": f"{round(float_rotation*100,1)}%", "impact": 12})

            # --- SCORE SAFETY CAP (STAGE 2) ---
            # Modules 2, 4, 7, and Float Rotation Bonuses Capped at 35
            stage2_bonuses = liq_accel_bonus + accumulation_bonus + rvol_bonus + float_rotation_bonus
            if stage2_bonuses > 35:
                clamped_val = 35
                reasons.append({"text": "Stage 2 Bonus Safety Cap Applied", "type": "neutral", "label": "SAFETY", "value": f"{stage2_bonuses} -> 35"})
                # Pro-rata reduction or simple clamp for total score consistency
                # We'll just adjust the accumulation_bonus for internal consistency in the report
                # but the final score will use the clamped Stage 2 sum.
                # For simplicity in this engine, we'll track a 'stage2_adj'
            
            # Phase 2: Technical Setup & Execution
            # Module 8: Base Weighted Scoring
            # Normalization Helper
            def normalize(val, min_v, max_v):
                if max_v == min_v: return 0.5
                return max(0, min(1, (val - min_v) / (max_v - min_v)))
            
            # Enhancement: Volatility Expansion Check
            if atr_ratio > 1.3:
                volatility_bonus = 8
                reasons.append({"text": "Volatility Expansion Breakout", "type": "positive", "label": "VOL", "value": f"{round(atr_ratio,2)}x", "impact": 8})
            

            # Module 10: ADX Standard Bonus
            if adx_val > 25 and adx_slope > 0: trend_bonus = 10
            if trend_direction_state == "BULLISH_TREND": trend_dir_bonus = 8

            # --- PHASE 2: Global Momentum Cap & Final Scoring ---
            
            # V6.3 Global Momentum Cap Rule
            if (liquidity_acceleration_state == "ACCELERATION_CONFIRMED" and rvol_val >= 2.5 and vwap_reclaim_bonus > 0 and adx_val > 25 and adx_is_rising):
                inst_mom_total = (liq_accel_bonus + rvol_bonus + vwap_reclaim_bonus + vwap_bonus + accumulation_bonus + sector_bonus)
                if inst_mom_total > 45:
                    scale = 45.0 / inst_mom_total
                    liq_accel_bonus *= scale
                    rvol_bonus *= scale
                    vwap_reclaim_bonus *= scale
                    vwap_bonus *= scale
                    accumulation_bonus *= scale
                    sector_bonus *= scale
                    reasons.append({"text": "Institutional Momentum Cap Applied", "type": "neutral", "label": "GUARD", "value": f"{round(inst_mom_total,1)} -> 45.0", "impact": 0})

            # Bonus & Penalty Consolidation (Modules 1-14)
            # Stage 2 Safe Bonuses (Modules 2, 4, 7, and Float Rotation)
            stage2_bonuses_raw = liq_accel_bonus + accumulation_bonus + rvol_bonus + float_rotation_bonus
            stage2_clamped = min(stage2_bonuses_raw, 35)
            
            # Update reasons if clamped (Optional: already did it above but let's ensure score sync)
            stage2_diff = stage2_clamped - stage2_bonuses_raw
            
            m1_8_bonus_total = (pullback_bonus + reclaim_bonus + sweep_bonus + squeeze_bonus + gap_bonus + poc_bonus + fan_bonus + inst_bonus + mtf_bonus + acc_bonus + institutional_volume_bonus + trend_bonus + vwap_reclaim_bonus + trend_dir_bonus + sector_bonus + vol_acc_bonus + daily_momentum_bonus + ad_bonus + vwap_bonus + breadth_bonus + volatility_bonus + stage2_clamped)
            m1_8_penalty_total = (exhaustion_penalty + context_penalty + overheat_penalty + chop_penalty + volume_penalty + structure_penalty + fake_breakout_penalty + vwap_ext_penalty + trend_penalty + trap_penalty + trend_dir_penalty + sector_penalty_v6_3 + abs(liq_accel_penalty) + regime_adj + mtf_penalty + liquidity_bonus + breadth_penalty)
            
            # Module 8: Base Weighted Scoring
            vol_ma_5m = df_5m['volume'].rolling(20).mean().iloc[-1]
            volume_expansion_ratio = df_5m['volume'].iloc[-1] / vol_ma_5m if vol_ma_5m > 0 else 1.0
            base_score_weighted = (vwap_score*0.30) + (adx_score*0.25) + (pa_score*0.25) + (volume_expansion_ratio*10*0.20)
            
            final_score_pre_timing = base_score_weighted + m1_8_bonus_total + m1_8_penalty_total
            
            # Final Volume Validation
            if rvol_val < 1.0 and final_score_pre_timing >= 78:
                block_trade, block_reason = True, "Volume Validation Block"

            if not block_trade:
                # Module 13: Time-of-Day Beta / Optimal Window
                scan_window = self._is_optimal_window(now_timing)
                timing_bonus = 3 if (scan_window == "OPTIMAL" and final_score_pre_timing >= 70) else 0
                final_score = round(max(0, min(160, final_score_pre_timing + timing_bonus)), 1)
                
                # Module 9: Signal Hierarchy
                if final_score >= 105: signal_type = "PIONEER PRIME 🏆"
                elif final_score >= 92: signal_type = "HIGH CONVICTION BUY 👑"
                elif final_score >= 78: signal_type = "BUY SETUP ✅"
                elif final_score >= 67: signal_type = "WATCHLIST ⚖"
                else: signal_type = "IGNORE 🚫"

                confidence_label = f"{round(final_score/1.6,1)}% Probability"
                logic_signal = "BUY" if final_score >= 78 else "NEUTRAL"
                msg = f"DEBUG: {sym} | Score: {final_score} | SIGNAL: {signal_type} | ADX: {round(adx_val,1)}\n"
                
            # --- Blocking & Result Mapping ---
            if block_trade:
                signal_type, final_score = "IGNORE 🚫", 0
                confidence_label, logic_signal = block_reason, "NEUTRAL"
                msg = f"DEBUG: {sym} | Score: 0 | BLOCKED by {block_reason} | ADX: {round(adx_val,1)}\n"
            
            with open("intraday_debug.log", "a", encoding='utf-8') as f: f.write(msg)
            
            target_val = ta_15m.get("resistance", real_price * 1.02)
            stop_val = ta_15m.get("support", real_price * 0.99)
            setup_tag = ""
            if "PRIME" in signal_type: setup_tag += " [💎 PRIME]"
            if mtf_ctx.get("is_bullish"): setup_tag += " [🌀 1H ALIGN]"

            return {
                "symbol": sym, "price": real_price, "score": final_score,
                "signal": logic_signal, "signal_type": signal_type,
                "verdict": f"{signal_type} ({confidence_label})",
                "setup_tag": setup_tag, "reasons": reasons[:8],
                "target": round(target_val, 2), "stop_loss": round(stop_val, 2),
                "rvol": round(rvol_val, 2), "adv20": round(adv20, 0),
                "vwap_deviation": round(vwap_deviation_pct, 2),
                "market_regime": regime, "trend_state": trend_direction_state,
                "alpha_intel": {
                    "growth_probability": confidence_label,
                    "risk_level": "Low" if final_score > 90 else "High" if final_score < 60 else "Medium",
                    "confidence": f"{round(final_score/1.6,1)}%"
                },
                "pioneer_prime_flag": "PRIME" in signal_type,
                "volume_expansion_ratio": round(volume_expansion_ratio, 2),
                "institutional_volume_flag": rvol_val >= 2.0,
                "scan_window": scan_window if not block_trade else "NORMAL",
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
