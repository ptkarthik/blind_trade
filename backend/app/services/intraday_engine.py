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
        self.semaphore = asyncio.Semaphore(5)
        self.job_states = {} # Stores state per job_id to prevent collisions

    async def _get_index_context(self):
        """Analyze Nifty 50 for overall market bias."""
        try:
            # Look at Nifty 50 for general market trend
            df = await market_service.get_ohlc("^NSEI", period="2d", interval="15m")
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

    async def analyze_stock(self, sym: str):
        """
        Professional Intraday Analysis with Multi-Timeframe & Market Context.
        """
        try:
            # 1. Fetch High-Frequency Data (15m for Trend, 5m for Timing)
            df_15m = await market_service.get_ohlc(sym, period="5d", interval="15m")
            df_5m = await market_service.get_ohlc(sym, period="2d", interval="5m")
            
            price_data = await market_service.get_live_price(sym)
            real_price = price_data.get("price", 0.0)
            
            if df_15m.empty or len(df_15m) < 40 or real_price <= 0:
                return None

            # 2. Market Context (Index Filter)
            index_ctx = await self._get_index_context()
            
            # --- INSTITUTIONAL INTEL (Paid App Features for Intraday) ---
            # Needs Daily Data
            df_daily = await market_service.get_ohlc(sym, period="1y", interval="1d")
            
            from app.services.institutional_intel import institutional_intel
            inst_data = await asyncio.to_thread(institutional_intel.analyze, df_daily)
            
            rs_rating = inst_data.get("rs_rating", 50)
            spon_action = inst_data.get("institutional_action", "Neutral")
            
            # 3. Technical Analysis (Intraday Mode)
            # 15m Trend & Level detection
            ta_15m = await asyncio.to_thread(ta_intraday.analyze_stock, df_15m)
            if not ta_15m: return None
            
            # 5m Momentum & Entry timing
            ta_5m = await asyncio.to_thread(ta_intraday.analyze_stock, df_5m)
            
            # 4. Professional Weighted Scoring
            # Trend Alignment (30%) - Price vs VWAP/50EMA on 15m
            trend_score = ta_15m.get("trend_score", 50)
            
            # Momentum Confirmation (20%) - RSI/MACD on 5m (Entry timeframe)
            mom_score = ta_5m.get("mom_score", 50) if ta_5m else ta_15m.get("mom_score", 50)
            
            # Volume Strength (20%)
            vol_score = ta_15m.get("vol_score", 50)
            
            # Support/Resistance Position (15%)
            safety_score = ta_15m.get("safety_score", 50)
            
            # Market Context (15%)
            index_score = index_ctx["score"]
            
            # Institutional Bonus (Intraday Bias)
            inst_bonus = 0
            if rs_rating > 80: inst_bonus += 10 # Trade with Leaders
            if "Accumulation" in spon_action: inst_bonus += 5 # Buy Dips
            if "Distribution" in spon_action: inst_bonus -= 10 # Avoid Longs
            
            # Aggregation
            final_score = (trend_score * 0.30) + (mom_score * 0.20) + (vol_score * 0.20) + \
                          (safety_score * 0.15) + (index_score * 0.15) + \
                          inst_bonus
            
            final_score = round(max(0, min(100, final_score)), 1)

            # 5. Signal & Confidence Labels
            signal_type = "WATCHLIST"
            confidence_label = "Avoid"
            
            if final_score >= 90:
                signal_type = "STRONG BUY"
                confidence_label = "High Probability"
            elif final_score >= 75:
                signal_type = "BUY"
                confidence_label = "Confirmed Setup"
            elif final_score >= 60:
                signal_type = "NEUTRAL"
                confidence_label = "Watchlist / Pullback"
            elif final_score <= 35:
                signal_type = "SELL"
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
                reasons.extend(ta_15m["groups"]["Trend"]["details"])
                reasons.extend(ta_15m["groups"]["Volume"]["details"])
                reasons.extend(ta_15m["groups"]["Risk & Levels"]["details"])
            
            if ta_5m:
                reasons.extend(ta_5m["groups"]["Momentum"]["details"])
            
            # Add Market Context Detail
            reasons.append({
                "text": f"Index Context: {index_ctx['bias']}",
                "type": "positive" if index_score > 50 else "negative" if index_score < 50 else "neutral",
                "label": "MACRO",
                "value": "Nifty 50"
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
            verdict = f"INTRA: {signal_type} ({confidence_label}){inst_tag}. [💡 ENTRY] {entry_analysis.get('rationale', 'Standard entry.')}"
            rationale = ta_15m.get("target_reason", "Technical Setup Confirmed.")

            return {
                "symbol": sym.upper(),
                "price": real_price,
                "score": final_score,
                "signal": "BUY" if "BUY" in signal_type else "SELL" if "SELL" in signal_type else "NEUTRAL",
                "intraday_signal": signal_type, # Specific label like STRONG BUY
                "confidence_label": confidence_label,
                "verdict": verdict,
                "strategic_summary": verdict, # Align with frontend mapping
                "rationale": rationale,
                "reasons": reasons[:8], # Top 8 most relevant reasons
                "support": ta_15m.get("support", 0),
                "target": ta_15m.get("resistance", 0),
                "stop_loss": ta_15m.get("support", 0), 
                "entry": entry_analysis.get("entry_price", real_price),
                "entry_analysis": entry_analysis,
                "sector": price_data.get("sector", "General"),
                "change": price_data.get("change", 0.0),
                "change_percent": price_data.get("change_percent", 0.0),
                "market_cap": price_data.get("market_cap", "N/A"),
                "analysis_mode": "intraday",
                "groups": ta_15m.get("groups", {}),
                "alpha_intel": {
                    "growth_probability": confidence_label,
                    "risk_level": "Low" if safety_score > 70 else "High" if safety_score < 40 else "Medium",
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
            symbols = list(STATIC_FULL_LIST)
            
        total = len(symbols)
        print(f"Intraday Engine: Starting Scan for Job {job_id} with {total} symbols")
        
        # 2. Initialize Per-Job State (Avoid Instance Collisions)
        self.job_states[job_id] = {
            "results": [],
            "active": [],
            "progress": 0,
            "is_running": True
        }

        # 3. Start Decoupled Progress Sync Loop
        # This prevents SQLite locks and gives real-time batch visibility
        sync_task = asyncio.create_task(self._progress_loop(job_id, total))

        try:
            # 4. Iterate with Semaphore
            async def sem_task(sym, idx):
                async with self.semaphore:
                    # Defensive: Extract symbol string if discovery gave us objects
                    symbol_str = sym["symbol"] if isinstance(sym, dict) else sym

                    # Periodically check if job was stopped/paused
                    if idx % 5 == 0:
                        async with AsyncSessionLocal() as session:
                            stmt = select(Job).where(Job.id == job_id)
                            res = await session.execute(stmt)
                            job_obj = res.scalars().first()
                            if job_obj and job_obj.status == "stopped":
                                return

                    state = self.job_states[job_id]
                    state["active"].append(symbol_str)
                    try:
                        res = await self.analyze_stock(symbol_str)
                        if res:
                            state["results"].append(res)
                    except Exception as e:
                        print(f"Intraday Scan Error for {symbol_str}: {e}")
                    finally:
                        state["progress"] += 1
                        if symbol_str in state["active"]:
                            state["active"].remove(symbol_str)

            tasks = [sem_task(s, i) for i, s in enumerate(symbols)]
            await asyncio.gather(*tasks)
        finally:
            # 4. Cleanup
            self.scan_active = False
            
            # SIGNAL LOOP TO STOP
            if job_id in self.job_states:
                self.job_states[job_id]["is_running"] = False
            
            # Wait for it to finish gracefully
            await sync_task

        # 6. Final Output
        state = self.job_states.get(job_id, {"results": []})
        final_results = sorted(state["results"], key=lambda x: x.get("score", 0), reverse=True)
        final_payload = {
            "total_scanned": total,
            "progress": total,
            "total_steps": total,
            "success_count": len(final_results),
            "data": final_results,
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
                
                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    if job_obj:
                        active_str = ", ".join(state["active"][:3])
                        if len(state["active"]) > 3:
                            active_str += f" +{len(state['active'])-3}"
                        
                        current_result = job_obj.result or {}
                        current_result["progress"] = state["progress"]
                        current_result["total_steps"] = total
                        current_result["active_symbols"] = list(state["active"])
                        current_result["data"] = list(state["results"])
                        current_result["status_msg"] = f"Analyzing: {active_str}"
                        
                        job_obj.result = sanitize_data(current_result)
                        flag_modified(job_obj, "result")
                        job_obj.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception as e:
                print(f"Intraday Sync Warning: {e}")
            await asyncio.sleep(2.0)
        print(f"📡 Intraday Progress Sync stopped for {job_id}")

intraday_engine = IntradayEngine()
