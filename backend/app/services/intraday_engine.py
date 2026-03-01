import asyncio
import pandas as pd
import numpy as np
from app.services.market_data import market_service
from app.services.ta_intraday import ta_intraday
from app.services.utils import STATIC_FULL_LIST, sanitize_data
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from datetime import datetime

class IntradayEngine:
    """
    Specialized engine for Intraday Analysis.
    Focuses on 15-minute intervals, VWAP, and Momentum.
    """
    def __init__(self):
        self.semaphore = asyncio.Semaphore(15)
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

    async def _get_index_context(self):
        """Analyze Nifty 50 for overall market bias."""
        try:
            # Look at Nifty 50 for general market trend
            # FAST TIMEOUT to prevent Intraday Scan startup from hanging for 150+ seconds
            df = await asyncio.wait_for(
                market_service.get_ohlc("^NSEI", period="2d", interval="15m"),
                timeout=8.0
            )
            if df.empty: return {"score": 50, "bias": "Neutral"}
            
            # Simple bias: Price relative to EMA 20 on 15m
            from ta.trend import EMAIndicator
            ema20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
            close = df['close'].iloc[-1]
            
            if close > ema20 * 1.002: return {"score": 100, "bias": "Bullish"}
            if close < ema20 * 0.998: return {"score": 0, "bias": "Bearish"}
            return {"score": 50, "bias": "Neutral"}
        except:
            return {"score": 50, "bias": "Neutral"}

    async def analyze_stock(self, sym: str, job_id: str = None, global_index_ctx: dict = None, fast_fail: bool = False):
        """
        Professional Intraday Analysis with Multi-Timeframe & Market Context.
        """
        try:
            # CHECK STOP 1
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # 1. Fetch 5m OHLC & ABSOLUTE LATEST Price (Fixes Kite Discrepancy)
            ohlc_task = market_service.get_ohlc(sym, period="5d", interval="5m", fast_fail=fast_fail)
            live_price_task = market_service.get_latest_price(sym)
            df_5m, live_price = await asyncio.gather(ohlc_task, live_price_task)
            
            if df_5m is None or df_5m.empty or len(df_5m) < 40:
                print(f"⚠️ Intraday Analysis skipped for {sym}: Insufficient data (5m).")
                return None
            
            # Use Live price if valid, else fallback to latest candle close
            real_price = live_price if live_price > 0 else df_5m['close'].iloc[-1]
            if real_price <= 0: return None

            # 2. Resample 5m to 15m Locally
            logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
            df_15m = df_5m.resample('15min').agg(logic).dropna()
            
            if len(df_15m) < 20:
                print(f"⚠️ Intraday skipped for {sym}: Not enough 15m data after resampling.")
                return None
                
            index_ctx = global_index_ctx if global_index_ctx else {"score": 50, "bias": "Neutral"}

            # CHECK STOP 3
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # --- INSTITUTIONAL INTEL (Bypassed for Speed) ---
            rs_rating = 50
            spon_action = "Neutral"

            # CHECK STOP 4
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None
            
            # 3. Technical Analysis (Intraday Mode)
            # 15m Trend & Level detection
            ta_15m = await asyncio.to_thread(ta_intraday.analyze_stock, df_15m)
            if not ta_15m: return None
            
            # 5m Momentum & Entry timing
            ta_5m = await asyncio.to_thread(ta_intraday.analyze_stock, df_5m)
            
            # 4. Professional Weighted Scoring (User 5-Indicator Custom Algorithm)
            vwap_score = ta_15m.get("vwap_score", 50)
            rvol_score = ta_15m.get("rvol_score", 50)
            pa_score = ta_15m.get("pa_score", 50)
            pivot_score = ta_15m.get("pivot_score", 50)
            
            # User noted EMAs are best on 1m, 3m, 5m. Use 5m if available
            ema_score = ta_5m.get("ema_score", 50) if ta_5m else ta_15m.get("ema_score", 50)
            
            # Market Context (Bonus/Malus applied later outside the 100% boundary)
            index_score = index_ctx.get("score", 50)
            
            # Institutional Bonus (Intraday Bias)
            inst_bonus = 0
            if rs_rating > 80: inst_bonus += 5 # Trade with Leaders
            if "Accumulation" in spon_action: inst_bonus += 2 # Buy Dips
            if "Distribution" in spon_action: inst_bonus -= 5 # Avoid Longs
            
            # Daily Momentum Guardrail
            # Prevent incredibly strong daily stocks (>3% up) from being marked as Intraday SELLs due to minor pullbacks
            day_change_pct = 0
            today_date = df_5m.index[-1].date()
            prev_days_df = df_5m[df_5m.index.date < today_date]
            if not prev_days_df.empty:
                prev_close = prev_days_df['close'].iloc[-1]
                day_change_pct = ((real_price - prev_close) / prev_close) * 100
            else:
                today_open = df_5m[df_5m.index.date == today_date]['open'].iloc[0]
                day_change_pct = ((real_price - today_open) / today_open) * 100
                
            daily_momentum_bonus = 0
            if day_change_pct > 4.0:
                daily_momentum_bonus = 20
            elif day_change_pct > 2.0:
                daily_momentum_bonus = 10
            elif day_change_pct < -4.0:
                daily_momentum_bonus = -20
            elif day_change_pct < -2.0:
                daily_momentum_bonus = -10
            
            # EXACT User Defined Weighting (100% Base Score)
            # VWAP (30%), RVOL (25%), Order Flow/PA Proxy (20%), Pivots (15%), EMA (10%)
            base_internal_score = (vwap_score * 0.30) + (rvol_score * 0.25) + (pa_score * 0.20) + \
                                  (pivot_score * 0.15) + (ema_score * 0.10)
                                  
            # Add External Market context and bonuses
            final_score = base_internal_score + inst_bonus + daily_momentum_bonus
            
            # Minor macro adjustment overlay
            if index_score > 75: final_score += 5
            elif index_score < 40: final_score -= 5
            
            final_score = round(max(0, min(100, final_score)), 1)
            
            # Floor/Ceiling Guardrails to avoid counter-trend recommendations
            if day_change_pct > 3.0:
                final_score = max(50.0, final_score) # Prevent SELL signal if deeply green on the day
            elif day_change_pct < -3.0:
                final_score = min(50.0, final_score) # Prevent BUY signal if deeply red on the day

            # 5. Signal & Confidence Labels
            signal_type = "NEUTRAL"
            confidence_label = "Avoid"
            
            if final_score >= 85:
                signal_type = "STRONG BUY"
                confidence_label = "High Probability"
            elif final_score >= 70:
                signal_type = "BUY"
                confidence_label = "Confirmed Setup"
            elif final_score >= 55:
                signal_type = "NEUTRAL"
                confidence_label = "Watchlist / Pullback"
            elif final_score >= 40:
                signal_type = "SELL"
                confidence_label = "Weakness"
            else:
                signal_type = "STRONG SELL"
                confidence_label = "Bearish Momentum"
            
            # --- INVESTMENT ADVISOR ENGINE (New Integration) ---
            from app.services.advisor_engine import advisor_engine
            # We treat Intraday 'fund' as just live price data for now since we don't do full fundamental scans for 15m
            advisory = advisor_engine.generate_advice(
                sym, real_price, {"score": final_score}, ta_15m, {}, {}, None, mode="intraday"
            )

            # 6. Extract Details for UI
            reasons = []
            if "groups" in ta_15m:
                reasons.extend(ta_15m["groups"]["VWAP"]["details"])
                reasons.extend(ta_15m["groups"]["Volume"]["details"])
                reasons.extend(ta_15m["groups"]["Price Action"]["details"])
                reasons.extend(ta_15m["groups"]["Risk & Levels"]["details"])
            
            # Overlay 5m Trend Details if available
            if ta_5m and "groups" in ta_5m:
                reasons.extend(ta_5m["groups"]["Trend"]["details"])
            elif "groups" in ta_15m:
                reasons.extend(ta_15m["groups"]["Trend"]["details"])
            
            # Add Market Context Detail
            reasons.append({
                "text": f"Index Context: {index_ctx['bias']}",
                "type": "positive" if index_score > 50 else "negative" if index_score < 50 else "neutral",
                "label": "MACRO",
                "value": "Nifty 50"
            })
            
            # Add Daily Momentum Context
            if abs(day_change_pct) >= 2.0:
                reasons.append({
                    "text": f"Strong Daily Momentum" if day_change_pct > 0 else "Weak Daily Momentum",
                    "type": "positive" if day_change_pct > 0 else "negative",
                    "label": "DAY TREND",
                    "value": f"{day_change_pct:+.2f}%"
                })
            
            # Add Institutional Context Detail
            if rs_rating > 80:
                reasons.append({
                    "text": f"Market Leader (RS {rs_rating})",
                    "type": "positive",
                    "label": "INSTITUTIONAL",
                    "value": "Top 20%"
                })
            if "Accumulation" in spon_action:
                reasons.append({
                    "text": "Institutional Accumulation Detected",
                    "type": "positive",
                    "label": "INSTITUTIONAL",
                    "value": "Big Money Buying"
                })

            # Verdict & Rationale
            entry_analysis = advisory.get("entry_analysis", {})
            inst_tag = ""
            if rs_rating > 85: inst_tag = f" [🔥 LEADER RS{rs_rating}]"
            
            # NEW: Professional Setup Tags
            setup_tag = ""
            orb = ta_15m.get("orb", {})
            gap = ta_15m.get("gap", {})
            
            if orb.get("status") == "Breakout": setup_tag += " [🚀 ORB BREAKOUT]"
            elif orb.get("status") == "Breakdown": setup_tag += " [⚠️ ORB BREAKDOWN]"
            
            if gap.get("type") == "Gap Up": setup_tag += " [⚡ GAP UP]"
            elif gap.get("type") == "Gap Down": setup_tag += " [🔻 GAP DOWN]"

            vwap_val = ta_15m.get("vwap_val", 0)
            if real_price > vwap_val * 1.01: setup_tag += " [✅ >VWAP]"
            elif real_price < vwap_val * 0.99: setup_tag += " [❌ <VWAP]"

            # --- RISK MANAGEMENT (Intraday) ---
            from app.services.risk_sentiment import risk_engine
            
            if "SELL" in signal_type:
                target_val = ta_15m.get("support", 0)
                stop_val = ta_15m.get("resistance", 0)
            else:
                target_val = ta_15m.get("resistance", 0)
                stop_val = ta_15m.get("support", 0)
            
            trade_params = risk_engine.calculate_trade_params(real_price, stop_val, target_val)
            if trade_params.get("is_good_rr"):
                setup_tag += f" [⚖️ R:R {trade_params['rr_ratio']}]"

            verdict = f"INTRA: {signal_type} ({confidence_label}){inst_tag}{setup_tag}. [💡 ENTRY] {entry_analysis.get('rationale', 'Standard entry.')}"
            rationale = ta_15m.get("target_reason", "Technical Setup Confirmed.")

            # Calculate change using open price of the last day
            try:
                last_day = df_5m.index[-1].date()
                last_day_df = df_5m[df_5m.index.date == last_day]
                open_price = last_day_df['open'].iloc[0]
                change = real_price - open_price
                change_percent = (change / open_price) * 100
            except:
                change = 0.0
                change_percent = 0.0

            return {
                "symbol": sym.upper(),
                "price": real_price,
                "score": final_score,
                "signal": "BUY" if "BUY" in signal_type else "SELL" if "SELL" in signal_type else "NEUTRAL",
                "intraday_signal": signal_type,
                "confidence_label": confidence_label,
                "verdict": verdict,
                "strategic_summary": verdict,
                "rationale": rationale,
                "reasons": reasons[:8],
                "support": stop_val,
                "target": target_val,
                "stop_loss": stop_val, 
                "entry": entry_analysis.get("entry_price", real_price),
                "entry_analysis": entry_analysis,
                "risk_management": trade_params,
                "sector": market_service.get_sector_for_symbol(sym),
                "change": round(float(change), 2),
                "change_percent": round(float(change_percent), 2),
                "market_cap": "N/A",
                "analysis_mode": "intraday",
                "groups": ta_15m.get("groups", {}),
                "orb": orb,
                "gap": gap,
                "alpha_intel": {
                    "growth_probability": confidence_label,
                    "risk_level": "Low" if final_score > 70 else "High" if final_score < 40 else "Medium",
                    "valuation_status": "Intraday Momentum",
                    "suggested_hold": "Day Trade (Exit by 3:15 PM)",
                    "confidence": f"{final_score}%"
                }
            }

        except Exception as e:
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

        # 6. Final Output
        state = self.job_states.get(job_id, {"results": [], "failed_symbols": []})
        final_results = sorted(state["results"], key=lambda x: x.get("score", 0), reverse=True)
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
