import asyncio
import pandas as pd
import numpy as np
import time
from app.services.market_data import market_service
from app.services.index_context import index_ctx
from app.services.liquidity_service import liquidity_service
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
        
        # 🚩 [V12.8] INSTITUTIONAL SCORING FLAGS
        self.SCORING_FLAGS = {
            "enable_smooth_alpha": True,
            "enable_dynamic_ema": True,
            "enable_vwap_precision": True,
            "enable_adx_di_validation": True,
            "enable_phantom_pre_filter": True,
            "enable_sideways_regime": True,
            "enable_time_decay": True,
            "enable_mtf_bonus": True,
            "enable_dna_gate": True,
            "enable_pa_scaling": True,
            "enable_momentum_leader": True,
            "enable_extended_structure": True,
            "enable_dynamic_dna": True,
            "debug_dna_mode": True,
            "enable_dynamic_alpha": True,
            "debug_alpha_mode": True
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
        except: return {"score": 50, "market_regime": "Mixed"}

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

            if indicators["price"] < indicators["ema20"]:
                return {
                    "symbol": sym,
                    "score": 0,
                    "signal": "IGNORE",
                    "reason": "Below EMA20 (Trend Broken)"
                }

            # =========================
            # STEP 2: LAYER 1 (DNA)
            # =========================
            l1_score, l1_data = self._run_layer1(indicators)

            # =========================
            # STEP 3: DNA GATE
            # =========================
            if l1_score < 20:
                l2_score = 0
                l2_data = {"alpha_mode": "NONE", "reason": "DNA Gate Blocked"}
            else:
                l2_score, l2_data = self._run_layer2(indicators, df_15m, df_1h)

            # =========================
            # STEP 4: LAYER 3
            # =========================
            l3_penalty, l3_data = self._run_layer3(indicators, df_15m, global_index_ctx)

            # =========================
            # FINAL SCORE
            # =========================
            final_score = max(0, min(100, (l1_score + l2_score - l3_penalty)))
            signal = self._get_signal(final_score)

            # Compatibility: build "reasons" list and "groups" for UI
            reasons = []
            for r in l1_data.get("reasons", []):
                reasons.append({"text": r, "type": "positive", "layer": 1, "impact": 5})
            for r in l2_data.get("reasons", []):
                reasons.append({"text": r, "type": "positive", "layer": 2, "impact": l2_score})
            for r in l3_data.get("reasons", []):
                reasons.append({"text": r, "type": "negative", "layer": 3, "impact": -5})

            groups = {
                "DNA (40%)": {"score": l1_score, "max": 40, "details": [r for r in reasons if r["layer"] == 1]},
                "Alpha Edge (60%)": {"score": l2_score, "max": 60, "details": [r for r in reasons if r["layer"] == 2]},
                "Safeguards (L3)": {"score": -l3_penalty, "max": 0, "details": [r for r in reasons if r["layer"] == 3]}
            }

            return {
                "symbol": sym, 
                "price": round(real_price, 2), 
                "score": round(final_score, 1),
                "signal": signal, 
                "signal_label": f"{signal} {('🏆' if final_score > 85 else '✅')}", 
                "verdict": "PIONEER PRIME" if final_score >= 85 else "Standard Setup",
                "reasons": reasons,
                "groups": groups,
                "entry": round(real_price, 2),
                "target": round(real_price + (indicators.get("atr", 0) * 1.5), 2),
                "stop_loss": round(real_price - indicators.get("atr", 1.0), 2),
                "alpha_mode": l2_data.get("mode", "NONE")
            }
        except Exception as e:
            return {"symbol": sym, "skip_reason": f"Analysis Error: {str(e)}"}

    def _get_indicators(self, df_15m, df_1h):
        ind_15m = self._compute_indicators(df_15m)
        if ind_15m is None: return None
        
        try:
            ema_1h_series = EMAIndicator(close=df_1h['close'], window=20).ema_indicator()
            ema_1h = ema_1h_series.iloc[-1]
            ema_1h_prev = ema_1h_series.iloc[-2]
            ema_1h_trend_up = ema_1h > ema_1h_prev
        except:
            ema_1h_trend_up = False
            
        return {**ind_15m, "ema_1h_trend_up": ema_1h_trend_up}

    def _compute_indicators(self, df: pd.DataFrame):
        df = df.copy().tail(100)
        price = df['close'].iloc[-1]
        
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = df.groupby(df.index.date).apply(lambda x: (x['typical_price'] * x['volume']).cumsum() / x['volume'].cumsum()).reset_index(level=0, drop=True)
        vwap = df['vwap'].iloc[-1]
        distance_vwap = ((price - vwap) / vwap) * 100
        
        ema20_series = EMAIndicator(close=df['close'], window=20).ema_indicator()
        ema20 = ema20_series.iloc[-1]
        ema_slope = ema20_series.diff().rolling(3).mean().iloc[-1]
        
        avg_vol = df['volume'].rolling(20).mean()
        avg = avg_vol.iloc[-1]
        rvol = df['volume'].iloc[-1] / avg if avg > 0 else 0
        
        high, low = df['high'], df['low']
        hh = high.iloc[-1] > high.iloc[-2] > high.iloc[-3]
        hl = low.iloc[-1] > low.iloc[-2] > low.iloc[-3]
        structure_ok = hh and hl
        
        is_pullback = (price > ema20 and low.iloc[-1] <= ema20 * 1.01 and df['close'].iloc[-1] > df['close'].iloc[-2])
        
        atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        atr = atr_indicator.average_true_range().iloc[-1]
        
        if pd.isna(price) or pd.isna(ema20) or pd.isna(vwap) or pd.isna(rvol):
            return None
            
        return {"price": price, "ema20": ema20, "ema_slope": ema_slope, "vwap": vwap, "distance_vwap": distance_vwap, "rvol": rvol, "structure_ok": structure_ok, "is_pullback": is_pullback, "atr": atr}

    def _run_layer1(self, indicators):
        price, ema20, ema_slope = indicators["price"], indicators["ema20"], indicators["ema_slope"]
        distance_vwap, rvol = indicators["distance_vwap"], indicators["rvol"]
        score, reasons = 0, []
        
        if price > ema20: score += 5; reasons.append("Price above EMA20")
        if ema_slope > 0: score += 5; reasons.append("EMA20 trending up")
        
        if abs(distance_vwap) < 1.5: score += 5; reasons.append("Near VWAP (healthy trend)")
        elif distance_vwap > 1.5: score += 3; reasons.append("Extended from VWAP")
        
        if rvol > 2: score += 5; reasons.append("High RVOL (institutional volume)")
        elif rvol > 1.2: score += 3; reasons.append("Above avg volume")
        
        return score, {"score": score, "reasons": reasons}

    def _run_layer2(self, indicators, df_15m, df_1h):
        price, ema20, distance_vwap = indicators["price"], indicators["ema20"], indicators["distance_vwap"]
        rvol, structure_ok, is_pullback = indicators["rvol"], indicators["structure_ok"], indicators["is_pullback"]
        ema_1h_trend_up = indicators["ema_1h_trend_up"]
        score, reasons, alpha_mode = 0, [], "NONE"
        
        distance_vwap_abs = abs(distance_vwap)
        is_near_vwap, is_trending = distance_vwap_abs < 1.2, price > ema20
        
        if is_near_vwap and is_trending and structure_ok:
            alpha_mode = "EARLY"; score += 35; reasons.append("EARLY: Near VWAP + Trend + Structure")
        elif is_pullback:
            alpha_mode = "PULLBACK"; score += 25; reasons.append("PULLBACK: EMA retracement + recovery")
        elif is_trending and distance_vwap > 1.2 and rvol > 1.5:
            alpha_mode = "MOMENTUM"; score += 20; reasons.append("MOMENTUM: Strong trend + volume")
        else:
            reasons.append("No valid Alpha setup")
            
        if rvol > 2.5: score += 5; reasons.append("Booster: High RVOL")
        if ema_1h_trend_up: score += 5; reasons.append("Booster: 1H Trend Up")
        
        score = min(score, 60)
        return score, {"score": score, "mode": alpha_mode, "reasons": reasons}

    def _run_layer3(self, indicators, df_15m, market_ctx):
        price, ema20, rvol, atr = indicators["price"], indicators["ema20"], indicators["rvol"], indicators["atr"]
        penalty, reasons = 0, []
        
        if price < ema20: penalty += 35; reasons.append("Penalty: Below EMA20 (trend broken)")
        
        distance_ema = abs((price - ema20) / ema20) * 100
        if distance_ema < 0.5: penalty += 10; reasons.append("Penalty: Too close to EMA (chop risk)")
        
        if rvol < 1.2: penalty += 15; reasons.append("Penalty: Low RVOL (no institutional volume)")
        
        last_candle = df_15m.iloc[-1]; high, low, close = last_candle['high'], last_candle['low'], last_candle['close']
        candle_range = high - low
        if candle_range > 0 and (high - close) / candle_range > 0.5:
            penalty += 15; reasons.append("Penalty: Strong upper wick (selling pressure)")
            
        risk, reward = atr, atr * 1.5
        rr_ratio = reward / risk if risk > 0 else 0
        if rr_ratio < 1.2: penalty += 15; reasons.append("Penalty: Poor Risk/Reward")
        
        recent_highs, prev_high = df_15m['high'].iloc[-3:], df_15m['high'].iloc[-4]
        if recent_highs.max() <= prev_high: penalty += 5; reasons.append("Penalty: No momentum (stale move)")
        
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
        print(f"🛰️ [V11 RESTORED] Pulse Scan: {total} symbols")
        
        self.job_states[job_id] = {"results": [], "failed_symbols": [], "progress": 0, "is_running": True, "pause_requested": False, "main_task": asyncio.current_task()}
        index_ctx = await self._get_index_context()
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        try:
            # Process in Streaming Batches of 100
            chunk_size = 100
            for i in range(0, total, chunk_size):
                # [V12.1 STOP CHECK] 🛑
                if job_id in self.job_states and not self.job_states[job_id].get("is_running", True):
                    if logger: logger.warning(f"🛑 [INTRA] Stop Signal Received. Terminating job {job_id} at {i}/{total}.")
                    break

                # [V12.1 PAUSE CHECK] ⏸️
                while job_id in self.job_states and self.job_states[job_id].get("pause_requested"):
                    if not self.job_states[job_id].get("is_running", True): break
                    await asyncio.sleep(1)

                chunk = symbols[i:i + chunk_size]
                chunk_syms = [s["symbol"] if isinstance(s, dict) else s for s in chunk]
                
                print(f"🛰️ Pulse Batch: {i}/{total} ({len(chunk_syms)} symbols)")
                
                # 1. Fetch data for this specific batch (with 30s HARD TIMEOUT)
                try:
                    res_15m, res_prices = await asyncio.wait_for(
                        asyncio.gather(
                            market_service.get_batch_ohlc(chunk_syms),
                            market_service.get_batch_prices(chunk_syms)
                        ),
                        timeout=120.0
                    )
                except asyncio.TimeoutError:
                    print(f"⚠️ [V11 TIMEOUT] Batch {i} hung. Force-skipping to maintain engine flow.")
                    self.job_states[job_id]["progress"] += len(chunk)
                    continue

                batch_pulse = {}
                for s in chunk_syms:
                    batch_pulse[s] = {"15m": res_15m.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}

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
                                self.job_states[job_id]["results"].append(res)
                                if logger:
                                    # [V12.7 HIGH-TRANSPARENCY LOGGER]
                                    l1 = res.get("groups", {}).get("DNA (40%)", {}).get("score", 0)
                                    l2 = res.get("groups", {}).get("Alpha Edge (60%)", {}).get("score", 0)
                                    l3 = res.get("groups", {}).get("Safeguards (L3)", {}).get("score", 0)
                                    
                                    reasons = res.get("reasons", [])
                                    catalysts = [r["text"] for r in reasons if r.get("impact", 0) > 0 and r.get("layer") in [1, 2]]
                                    penalties = [r["text"] for r in reasons if r.get("impact", 0) < 0 and r.get("layer") == 3]
                                    
                                    logger.info(f"✅ {sym}: {res['score']:>5} | [L1:{l1:>4} | L2:{l2:>4} | L3:{l3:>5}] | {res['signal']} ({res.get('alpha_mode', 'NONE')})")
                                    if catalysts: logger.info(f"   └ 🚀 Catalysts: {', '.join(catalysts[:4])}")
                                    if penalties: logger.info(f"   └ 🛡️ Penalties: {', '.join(penalties[:4])}")
                            else:
                                if logger: logger.warning(f"⚠️ {sym}: Skipped. Reason: {res.get('skip_reason', 'Unknown')}")
                        except Exception as e:
                            if logger: logger.error(f"❌ {sym}: Analysis ERROR: {str(e)}")
                            pass
                        finally:
                            self.job_states[job_id]["progress"] += 1

                await asyncio.gather(*[sem_task(s) for s in chunk])
                
        finally:
            self.job_states[job_id]["is_running"] = False
            await sync_task

        results = sorted(self.job_states[job_id]["results"], key=lambda x: x["score"], reverse=True)
        return sanitize_data({"total": total, "success": len(results), "data": results})

    async def stop_job(self, job_id: str):
        """[V12.1 RESTORED] Programmatic termination signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["is_running"] = False
            print(f"🛑 Signal sent to stop job {job_id}")

    async def pause_job(self, job_id: str):
        """[V12.1] Pause terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"⏸️ Signal sent to pause job {job_id}")

    async def resume_job(self, job_id: str):
        """[V12.1] Resume terminal signal."""
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"▶️ Signal sent to resume job {job_id}")

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
                            "data": sorted(state["results"], key=lambda x: x["score"], reverse=True)[:100],
                            "status_msg": f"V11 Pulse Scan: {state['progress']}/{total}"
                        })
                        flag_modified(job, "result")
                        await session.commit()
            except: pass
            await asyncio.sleep(2.5)

intraday_engine = IntradayEngine()
