import asyncio
import random
from typing import Dict, Any, List
import pandas as pd
from app.services.market_data import market_service
from app.services.market_discovery import market_discovery
from app.services.ta_swing import ta_swing
import logging

logger = logging.getLogger(__name__)

class SwingEngine:
    def __init__(self):
        self.job_states = {} # { job_id: {"progress": int, "total_steps": int, "results": list, "failed_symbols": list, "status_msg": str} }

    def start_job(self, job_id: str):
        self.job_states[job_id] = {
            "progress": 0,
            "total_steps": 1, 
            "results": [],
            "failed_symbols": [],
            "errors": [],
            "status_msg": "Initializing swing scan...",
            "active_symbols": [],
            "target_count": 0,
            "stop_requested": False,
            "is_running": True,
            "last_data_sync": 0
        }

    def update_job_progress(self, job_id: str, new_progress: int, total_steps: int = None, status_msg: str = None, active_symbols: list = None):
        if job_id not in self.job_states:
            return
        
        state = self.job_states[job_id]
        if status_msg is not None:
            state["status_msg"] = status_msg
        if active_symbols is not None:
             state["active_symbols"] = active_symbols
             
        # Guard rails for progress
        safe_progress = min(new_progress, state.get("total_steps", new_progress))
        if safe_progress < state["progress"]:
             safe_progress = state["progress"]
             
        state["progress"] = safe_progress
        if total_steps is not None:
             state["total_steps"] = total_steps
             
    def add_job_result(self, job_id: str, result: dict):
        if job_id in self.job_states:
             if result not in self.job_states[job_id]["results"]:
                 self.job_states[job_id]["results"].append(result)

    def add_failed_symbol(self, job_id: str, symbol_info: dict):
        if job_id in self.job_states:
            self.job_states[job_id]["failed_symbols"].append(symbol_info)

    def stop_job(self, job_id: str):
         if job_id in self.job_states:
              self.job_states[job_id]["stop_requested"] = True
              self.job_states[job_id]["is_running"] = False
              main_task = self.job_states[job_id].get("main_task")
              if main_task:
                  main_task.cancel()

    async def analyze_stock(self, sym: str, job_id: str = None):
        """
        Executes a Swing Scan for a single stock using strictly 1D data.
        """
        try:
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # 1. Fetch 1D Data (Need 250 days minimum to accurately calculate SMA 200)
            df_1d = await market_service.get_ohlc(sym, period="1y", interval="1d")
            
            if df_1d is None or df_1d.empty or len(df_1d) < 200:
                print(f"⚠️ Swing Analysis skipped for {sym}: Need 200 days for SMA.")
                return None
            
            real_price = df_1d['close'].iloc[-1]
            if real_price <= 0: return None
            
            # 2. Check Swing Setup Rules
            swing_result = await asyncio.to_thread(ta_swing.analyze_swing, df_1d)
            
            if not swing_result["match"]:
                 # Filtering failed matches (e.g. price drops below SMA 200) automatically
                 return None
                 
            # 3. Pull minor metadata context (Optional)
            company_data = await market_service.get_fundamentals(sym)
            name = company_data.get("shortName", sym)
            sector = market_service.get_sector_for_symbol(sym)

            # 4. Pack successful setups
            return {
                "symbol": sym,
                "name": name,
                "sector": sector,
                "price": round(real_price, 2),
                "score": 100, # Swing logic is binary. 100% means True setup.
                "signal": "SWING BUY",
                "confidence": "Confirmed Breakdown Bounce",
                "reasons": swing_result.get("reasons", []),
                # Specific Logistics tracking for Swing Trading
                "entry": swing_result.get("entry", round(real_price, 2)),
                "stop_loss": swing_result.get("stop_loss"),
                "target": swing_result.get("target"),
                "hold_duration": swing_result.get("hold_duration")
            }

        except Exception as e:
            print(f"❌ Swing Analyzer Error for {sym}: {e}")
            return None

    async def run_scan(self, job_id: str):
        """
        Runs the Swing Engine algorithm concurrently across the active market.
        """
        self.start_job(job_id)
        
        try:
            state = self.job_states[job_id]
            self.update_job_progress(job_id, 5, 100, "Discovery: Analyzing market sectors...")

            full_list = await market_discovery.get_full_market_list()
            symbols = [s['symbol'] for s in full_list]
            
            if not symbols:
                 self.update_job_progress(job_id, 100, 100, "Scan Complete (No symbols found)")
                 return state

            # Remove problematic symbols
            exclusion_list = ['ADANIGREEN.NS', 'ADANIPOWER.NS']
            symbols = [s for s in symbols if s not in exclusion_list]

            random.shuffle(symbols)

            total_stocks = len(symbols)
            state["total_steps"] = total_stocks
            state["target_count"] = total_stocks

            state["main_task"] = asyncio.current_task()
            sync_task = asyncio.create_task(self._progress_loop(job_id, total_stocks))

            self.update_job_progress(job_id, 0, total_stocks, f"Preparing to swing scan {total_stocks} stocks...")

            concurrency_limit = 10
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def sem_task(sym, idx):
                if state.get("stop_requested"): return
                
                async with semaphore:
                    # Keep track of active batches
                    current_active = state.get("active_symbols", [])
                    if len(current_active) >= concurrency_limit:
                         current_active.pop(0)
                    current_active.append(sym)
                    
                    self.update_job_progress(
                         job_id, 
                         idx, 
                         total_stocks, 
                         f"Analyzing: {', '.join(current_active[:3])}...", 
                         current_active
                    )
                    
                    print(f"Processed {idx + 1}/{total_stocks}: {sym}", flush=True)

                    res = await self.analyze_stock(sym, job_id)
                    
                    if res:
                        self.add_job_result(job_id, res)
                    else:
                        # Log why the stock failed the strict logic rules
                        self.add_failed_symbol(job_id, {"symbol": sym, "reason": "Failed Setup Criteria or Missing Data"})

            tasks = [sem_task(sym, i) for i, sym in enumerate(symbols)]
            await asyncio.gather(*tasks)
            
        except asyncio.CancelledError:
            print(f"🛑 Swing Scan Job {job_id} CANCELLED")

            if state.get("stop_requested"):
                self.update_job_progress(job_id, state["progress"], state["total_steps"], "Scan Stopped by User")
            else:
                 self.update_job_progress(job_id, total_stocks, total_stocks, f"Swing Scan Complete. Found {len(state['results'])} setups.", [])

        except Exception as e:
             logger.error(f"Error in swing scan {job_id}: {str(e)}")
             if job_id in self.job_states:
                  self.update_job_progress(job_id, self.job_states[job_id]["progress"], status_msg=f"Error: {str(e)}")
        
        finally:
            if job_id in self.job_states:
                self.job_states[job_id]["is_running"] = False
            
            # Wait for progress loop to naturally exit
            if 'sync_task' in locals():
                await sync_task

        final_state = self.job_states.get(job_id, {})
        final_payload = {
            "total_scanned": final_state.get("total_steps", 0),
            "progress": final_state.get("progress", 0),
            "total_steps": final_state.get("total_steps", 0),
            "success_count": len(final_state.get("results", [])),
            "data": final_state.get("results", []),
            "failed_symbols": final_state.get("failed_symbols", []),
            "status_msg": "Completed"
        }
        
        if job_id in self.job_states: del self.job_states[job_id]
        
        from app.services.utils import sanitize_data
        return sanitize_data(final_payload)

    async def _progress_loop(self, job_id: str, total: int):
        """Background pulse for DB sync."""
        from sqlalchemy.orm.attributes import flag_modified
        from app.db.session import AsyncSessionLocal
        from app.models.job import Job
        from sqlalchemy import select
        from app.services.utils import sanitize_data
        from datetime import datetime
 
        while job_id in self.job_states and self.job_states[job_id].get("is_running"):
            try:
                state = self.job_states.get(job_id)
                if not state: break
                
                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    current_result = {}
                    if job_obj:
                        current_result = job_obj.result or {}
                        if not isinstance(current_result, dict): current_result = {}
                        
                        current_result["progress"] = state.get("progress", 0)
                        current_result["total_steps"] = total
                        current_result["active_symbols"] = list(state.get("active_symbols", []))
                        current_result["status_msg"] = state.get("status_msg", "")
                        
                        current_count = len(state.get("results", []))
                        last_sync = state.get("last_data_sync", 0)
                        
                        # Force a sync if condition met, OR if job is nearly done to flush everything
                        if current_count - last_sync >= 5 or current_count == total or state.get("progress") == total:
                            current_result["data"] = list(state.get("results", []))
                            current_result["failed_symbols"] = list(state.get("failed_symbols", []))
                            state["last_data_sync"] = current_count

                        job_obj.result = sanitize_data(current_result)
                        flag_modified(job_obj, "result")
                        job_obj.updated_at = datetime.utcnow()
                        await session.commit()
            except Exception as e:
                print(f"Swing Sync Warning: {e}")
            await asyncio.sleep(2.0)

    async def pause_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True

    async def resume_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False

swing_engine = SwingEngine()
