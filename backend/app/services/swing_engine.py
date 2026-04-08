import asyncio
import time
import random
from typing import Dict, Any, List
import pandas as pd
import logging
from datetime import datetime

from app.services.market_data import market_service
from app.services.market_discovery import market_discovery
from app.services.ta_swing import ta_swing, safe_scalar
from app.services.portfolio_engine import portfolio_engine
from app.services.trade_manager import trade_manager
from app.services.utils import sanitize_data

logger = logging.getLogger(__name__)

class SwingEngine:
    def __init__(self):
        self.job_states = {} # { job_id: {"progress": int, "total_steps": int, "results": list, "failed_symbols": list, "status_msg": str} }
        self.market_context = {"nifty_bullish": False, "nifty_sma50": 0, "nifty_price": 0}

    def start_job(self, job_id: str):
        self.job_states[job_id] = {
            "progress": 0,
            "total_steps": 1, 
            "results": [],
            "failed_symbols": [],
            "errors": [],
            "status_msg": "Initializing market-adaptive swing scan...",
            "active_symbols": [],
            "target_count": 0,
            "stop_requested": False,
            "pause_requested": False,
            "is_running": True,
            "last_data_sync": 0,
            "last_sync_time": time.time()
        }

    def update_job_progress(self, job_id: str, new_progress: int, total_steps: int = None, status_msg: str = None, active_symbols: list = None):
        if job_id not in self.job_states: return
        state = self.job_states[job_id]
        if status_msg is not None: state["status_msg"] = status_msg
        if active_symbols is not None: state["active_symbols"] = active_symbols
        safe_progress = min(new_progress, state.get("total_steps", new_progress))
        if safe_progress < state["progress"]: safe_progress = state["progress"]
        state["progress"] = safe_progress
        if total_steps is not None: state["total_steps"] = total_steps
             
    def add_job_result(self, job_id: str, result: dict):
        if job_id in self.job_states:
             if not any(r["symbol"] == result["symbol"] for r in self.job_states[job_id]["results"]):
                 self.job_states[job_id]["results"].append(result)

    def add_failed_symbol(self, job_id: str, symbol_info: dict):
        if job_id in self.job_states:
            self.job_states[job_id]["failed_symbols"].append(symbol_info)

    async def refresh_market_context(self):
        """Fetch NIFTY 50 trend to set the global strategy bias."""
        try:
            df_nifty = await market_service.get_ohlc("^NSEI", period="1y", interval="1d")
            if not df_nifty.empty and len(df_nifty) > 50:
                from ta.trend import SMAIndicator
                sma50_series = SMAIndicator(close=df_nifty['close'], window=50).sma_indicator()
                nifty_price = safe_scalar(df_nifty['close'].iloc[-1])
                nifty_sma50 = safe_scalar(sma50_series.iloc[-1])
                nifty_20d_price = safe_scalar(df_nifty['close'].iloc[-21])
                nifty_20d_return = ((nifty_price / nifty_20d_price) - 1) * 100 if nifty_20d_price > 0 else 0
                
                from ta.momentum import RSIIndicator
                nifty_rsi = safe_scalar(RSIIndicator(close=df_nifty['close'], window=14).rsi().iloc[-1])
                
                self.market_context = {
                    "nifty_bullish": nifty_price > nifty_sma50,
                    "nifty_sma50": nifty_sma50,
                    "nifty_price": nifty_price,
                    "nifty_rsi": nifty_rsi,
                    "nifty_exhausted": nifty_rsi > 75,
                    "nifty_20d_return": nifty_20d_return,
                    "nifty_change": nifty_price - safe_scalar(df_nifty['close'].iloc[-2])
                }
                logger.info(f"📊 Market Context: NIFTY {'Bullish' if self.market_context['nifty_bullish'] else 'Bearish'} (RSI: {round(nifty_rsi, 1)})")
        except Exception as e:
            logger.error(f"Failed to refresh market context: {e}")

    async def analyze_stock(self, sym: str, job_id: str = None):
        """
        Executes a Multi-Strategy Swing Scan (Pullback & Breakout).
        """
        try:
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None

            # 1. Fetch 1D Data (Need 250 days for SMA 200 durability)
            df_1d = await market_service.get_ohlc(sym, period="1y", interval="1d")
            if df_1d is None or df_1d.empty or len(df_1d) < 200: return None
            
            real_price = safe_scalar(df_1d['close'].iloc[-1])
            if real_price <= 0: return None
            
            # 2. Parallel Strategy Execution
            # We check both to allow for 'Conflict Resolution' based on Market Bias
            nifty_20d_ret = self.market_context.get("nifty_20d_return", 0)
            pb_result = await asyncio.to_thread(ta_swing.analyze_pullback, df_1d, nifty_20d_ret)
            
            # Breakout logic is only allowed if Nifty is Bullish OR stock is extremely strong
            # (Exception: We still analyze it to see if it's near high)
            bo_result = await asyncio.to_thread(ta_swing.analyze_breakout, df_1d, nifty_20d_ret)

            # 3. Conflict Resolution & Selection
            selected = None
            is_nifty_bullish = self.market_context.get("nifty_bullish", False)
            is_market_exhausted = self.market_context.get("nifty_exhausted", False)
            
            # Logic Override: If market is exhausted (RSI > 75), Force Pullback ONLY
            if is_market_exhausted:
                if pb_result["match"]:
                    selected = pb_result
                    selected["market_context"] = "OVERBOUGHT_RECOVERY"
                else:
                    return None # No breakouts at market tops
            
            # Logic:
            # - If both match:
            #   - If Nifty Bullish OR Near 20D High (<1%) -> Prefer BREAKOUT
            #   - Else -> Prefer PULLBACK
            # - If only one matches: return that one
            
            high_20 = safe_scalar(df_1d['high'].iloc[-21:-1].max())
            is_near_high = (high_20 - real_price) / max(high_20, 1) < 0.01

            if pb_result["match"] and bo_result["match"]:
                if is_nifty_bullish or is_near_high:
                    selected = bo_result
                else:
                    selected = pb_result
            elif bo_result["match"]:
                # Breakout only allowed if Nifty is Bullish or it's a 'Super Breakout'
                if is_nifty_bullish or is_near_high:
                    selected = bo_result
            elif pb_result["match"]:
                selected = pb_result
                
            if not selected: 
                # Optional: Silent for non-matches to avoid console spam, 
                # but we can add a very subtle indicator if needed.
                return None

            strategy_name = selected.get("strategy", "UNKNOWN")
            # --- HIGH VISIBILITY LOG FOR MATCHES ---
            # Using emojis to make matches stand out in the terminal
            icon = "🚀 [BREAKOUT]" if strategy_name == "BREAKOUT" else "📥 [PULLBACK]"
            print(f"{icon} {sym}: MATCH FOUND! (Price: {real_price}, Vol-Ratio: {round(selected.get('vol_ratio', 0), 2)})", flush=True)

            # Extract Stop Loss and Target from the selected strategy
            sl = selected.get("stop_loss", 0.0)
            target = selected.get("target", 0.0)

            # 4. Refined Scoring (Base 50)
            score = 50
            
            # Booster: Volume Surge (+20)
            vol_ratio = selected.get("vol_ratio", 1.0)
            if vol_ratio > 1.8: score += 20
            elif vol_ratio > 1.4: score += 10
            
            # Booster: SMA 50 Support (+15)
            if selected.get("strategy") == "PULLBACK":
                zone_val = next((r["value"] for r in selected.get("reasons", []) if r["label"] == "ZONE"), "")
                if "SMA 50" in zone_val: score += 15
            
            # Booster: Near High (+10)
            if is_near_high: score += 10
            
            # Strategy Priority Score (Dynamic Weighting)
            if is_nifty_bullish:
                bo_weight, pb_weight = 1.2, 1.0
            else:
                bo_weight, pb_weight = 0.7, 1.2
            
            strategy_weight = bo_weight if selected["strategy"] == "BREAKOUT" else pb_weight
            priority_score = score * strategy_weight
            
            final_score = round(min(100, priority_score), 1)
            
            # Confidence Level
            confidence = "LOW"
            if final_score >= 85: confidence = "HIGH"
            elif final_score >= 70: confidence = "MEDIUM"

            # 5. Metadata & Advisory
            company_data = await market_service.get_fundamentals(sym)
            name = company_data.get("shortName", sym)
            sector = market_service.get_sector_for_symbol(sym)

            from app.services.advisor_engine import advisor_engine
            advisory = advisor_engine.generate_advice(
                sym, real_price, company_data, {}, {}, {}, None, mode="swing"
            )

            # 6. Portfolio & Risk Management Integration
            if job_id and self.job_states.get(job_id, {}).get("stop_requested"): return None
            port_result = portfolio_engine.calculate_position_size(real_price, sl)
            
            # Update verdict with specific portfolio advice
            verdict = f"SWING ({selected['strategy']}): {selected['setup_type']} detected. "
            if selected.get("strategy") == "BREAKOUT":
                verdict += f"Hybrid Exit: Partial at {target} (1.5R), then trail via EMA 9. "
            else:
                verdict += f"Conservative Target at {target} (2R). "
            
            verdict += f"Ref Capital (1L) Allocation: {port_result['exposure_pct']}%."

            return {
                "symbol": sym,
                "name": name,
                "sector": sector,
                "price": round(real_price, 2),
                "score": final_score,
                "confidence": confidence,
                "strategy": selected["strategy"],
                "setup_type": selected["setup_type"],
                "signal": "BUY",
                "verdict": verdict,
                "strategic_summary": advisory.get('entry_analysis', {}).get('rationale', 'Confirmed structure.'),
                "entry": round(real_price, 2),
                "stop_loss": sl,
                "target": target,
                "is_hybrid": selected.get("is_hybrid_exit", False),
                "hold_duration": "2 to 21 Days",
                "priority": priority_score,
                "reasons": selected.get("reasons", []),
                # --- Position Sizing & Portfolio Metadata ---
                "risk_per_trade_pct": portfolio_engine.risk_per_trade_pct, 
                "position_size_type": "PORTFOLIO_CONSERVATIVE",
                "ref_capital": portfolio_engine.total_capital, 
                "risk_per_share": round(abs(real_price - sl), 2),
                "suggested_quantity": port_result["quantity"],
                "capital_required": port_result["capital_required"],
                "portfolio_exposure": port_result["exposure_pct"]
            }

        except Exception as e:
            logger.error(f"❌ Swing Analyzer Error for {sym}: {e}")
            return None

    async def run_scan(self, job_id: str, logger=None):
        self.start_job(job_id)
        
        # 0. Pre-Scan Risk Circuit Breakers
        # We check both the daily loss limit (2%) and the total portfolio risk limit (5%)
        # before starting a single scan.
        total_cap = portfolio_engine.total_capital
        
        if await trade_manager.check_daily_loss(total_cap) == "STOP_TRADING":
            self.update_job_progress(job_id, 100, 100, "⚠️ SCAN ABORTED: Daily Loss Limit Breached (2% Cap).")
            return {"status": "ABORTED", "reason": "DAILY_LOSS_LIMIT"}

        if await trade_manager.is_risk_limit_reached(total_cap):
            self.update_job_progress(job_id, 100, 100, "⚠️ SCAN ABORTED: Portfolio Risk Limit Reached (5% Cap).")
            return {"status": "ABORTED", "reason": "RISK_LIMIT_REACHED"}

        await self.refresh_market_context()
        
        try:
            state = self.job_states[job_id]
            self.update_job_progress(job_id, 5, 100, "Discovery: Syncing market universe...")

            full_list = await market_discovery.get_full_market_list()
            symbols = [s['symbol'] for s in full_list]
            
            if not symbols:
                 self.update_job_progress(job_id, 100, 100, "Scan Complete (Empty)")
                 return state

            exclusion_list = ['ADANIGREEN.NS', 'ADANIPOWER.NS']
            symbols = [s for s in symbols if s not in exclusion_list]
            random.shuffle(symbols)

            total_stocks = len(symbols)
            state = self.job_states.get(job_id)
            if not state:
                logger.error(f"Job state not found for {job_id}")
                return {"status": "error"}
            
            # [V12.2] Link main task for immediate cancellation
            state["main_task"] = asyncio.current_task()
            state["total_steps"] = total_stocks
                
            sync_task = asyncio.create_task(self._progress_loop(job_id, total_stocks))

            concurrency_limit = 15 # Increased for faster scanning
            semaphore = asyncio.Semaphore(concurrency_limit)

            async def sem_task(sym, idx):
                if state.get("stop_requested"): return

                # [V12.1 PAUSE CHECK] ⏸️
                while job_id in self.job_states and state.get("pause_requested"):
                    if state.get("stop_requested"): return
                    await asyncio.sleep(1)
                
                # [V12.2] Immediate Stop Guard
                if state.get("stop_requested"): return

                async with semaphore:
                    # [V12.2] Re-check after acquiring slot
                    if state.get("stop_requested"): return
                    current_active = state.get("active_symbols", [])
                    if len(current_active) >= 5: current_active.pop(0)
                    current_active.append(sym)
                    
                    # Log to database for UI
                    self.update_job_progress(job_id, idx, total_stocks, f"Analyzing: {sym} ({idx}/{total_stocks})", current_active)
                    
                    # Log to stdout for Debugging/Terminal Visibility
                    if idx % 50 == 0:
                        print(f"📡 [SCANNER] Progress: {idx}/{total_stocks} stocks analyzed...", flush=True)
                    
                    res = await self.analyze_stock(sym, job_id)
                    if res: self.add_job_result(job_id, res)
                    else: self.add_failed_symbol(job_id, {"symbol": sym})

            tasks = [sem_task(sym, i) for i, sym in enumerate(symbols)]
            await asyncio.gather(*tasks)
            
            # 5. Portfolio Finalization (The "Professional" Filter)
            # After all stocks are scanned, we use the PortfolioEngine to pick the absolute best.
            scan_results = state.get("data", [])
            
            # Select best trades based on risk/reward/ranking
            # Note: PortfolioEngine now tracks active positions internally
            selected_signals = portfolio_engine.select_trades(scan_results)
            
            # Build final executable plans (Quantity, Capital, etc.)
            trade_plan = portfolio_engine.build_trade_plan(selected_signals)

            # NOTE: Auto-registration removed. User must manually 'confirm' a trade 
            # for the engine to start tracking its lifecycle (stops, exits, etc.)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Global Scan Error: {e}")
        finally:
            if job_id in self.job_states: 
                self.job_states[job_id]["stop_requested"] = True
                self.job_states[job_id]["is_running"] = False
            if 'sync_task' in locals(): await sync_task

        # Return the finalized Trade Plan instead of raw signals
        final_payload = {
            "total_scanned": state.get("total_steps", 0),
            "raw_signal_count": len(scan_results),
            "trade_plan_count": len(trade_plan),
            "data": trade_plan, # This is now the executable list
            "status_msg": f"Adaptive Scan Complete: {len(trade_plan)} Trades Generated."
        }
        
        if job_id in self.job_states: del self.job_states[job_id]
        return sanitize_data(final_payload)

    async def manage_active_trades(self):
        """
        Daily Lifecycle Maintenance: Update active trades with latest market data.
        - Calculates Trailing Stops
        - Checks Time Stops
        - Triggers SL/TP Exits
        """
        active_trades = trade_manager.get_active_trades()
        if not active_trades:
            return

        logger.info(f"🛰️ Trade Manager: Updating {len(active_trades)} active positions...")
        all_symbols = [t["symbol"] for t in active_trades]
        
        market_stats = {}
        for sym in all_symbols:
            try:
                # Fetch 1D OHLC including technicals needed for trailing
                df = await market_service.get_ohlc(sym, period="1mo", interval="1d")
                if df is None or df.empty: continue
                
                # Fetch EMA 9/20 for Trailing Stops
                from ta.trend import EMAIndicator
                ema_9 = EMAIndicator(close=df['close'], window=9).ema_indicator().iloc[-1]
                ema_20 = EMAIndicator(close=df['close'], window=20).ema_indicator().iloc[-1]
                
                market_stats[sym] = {
                    "close": safe_scalar(df['close'].iloc[-1]),
                    "high": safe_scalar(df['high'].iloc[-1]),
                    "low": safe_scalar(df['low'].iloc[-1]),
                    "ema_9": safe_scalar(ema_9),
                    "ema_20": safe_scalar(ema_20)
                }
            except Exception as e:
                logger.error(f"Failed to fetch update data for {sym}: {e}")

        # Execute updates in bulk
        await trade_manager.update_trades(market_stats)
        logger.info("✅ Trade Manager: Portfolio maintenance complete.")

    async def execute_trade_suggestion(self, trade_data: Dict[str, Any]):
        """
        Manually 'Enters' a trade suggestion into the Portfolio/TradeManager.
        This transition from a 'Signal' to an 'Active Position'.
        """
        symbol = trade_data.get("symbol")
        if not symbol:
            return {"status": "ERROR", "message": "Invalid trade data."}
            
        # 1. Final Risk Check
        if await trade_manager.is_risk_limit_reached(portfolio_engine.total_capital):
            logger.warning(f"🚫 Cannot execute {symbol}: Portfolio risk limit reached.")
            return {"status": "BLOCKED", "message": "Risk limit reached."}
            
        # 2. Add to TradeManager (Lifecycle tracking starts)
        await trade_manager.add_trade(trade_data)
        
        # 3. Add to Portfolio (Capital/Sector tracking starts)
        portfolio_engine.update_active_positions(trade_data)
        
        return {"status": "SUCCESS", "message": f"Monitoring started for {symbol}."}

    async def _progress_loop(self, job_id: str, total: int):
        from sqlalchemy.orm.attributes import flag_modified
        from app.db.session import AsyncSessionLocal
        from app.models.job import Job
        from sqlalchemy import select
        
        while job_id in self.job_states and self.job_states[job_id].get("is_running"):
            try:
                state = self.job_states.get(job_id)
                if not state: break
                async with AsyncSessionLocal() as session:
                    stmt = select(Job).where(Job.id == job_id)
                    res = await session.execute(stmt)
                    job_obj = res.scalars().first()
                    if job_obj:
                        if job_obj.status == "stopped":
                            state["stop_requested"] = True
                            state["is_running"] = False
                            # [V12.2] Explicitly cancel the main execution task
                            main_task = state.get("main_task")
                            if main_task and not main_task.done():
                                main_task.cancel()
                            break
                        
                        # [V12.1 EXTERNAL PAUSE CHECK] ⏸️
                        if job_obj.status == "paused":
                            state["pause_requested"] = True
                        elif state.get("pause_requested") and job_obj.status == "processing":
                            state["pause_requested"] = False
                        
                        current_result = job_obj.result or {}
                        current_result.update({
                            "progress": state.get("progress", 0),
                            "total_steps": total,
                            "active_symbols": list(state.get("active_symbols", [])),
                            "status_msg": state.get("status_msg", ""),
                            "data": list(state.get("results", []))[-50:] # Keep last 50 matches live
                        })
                        job_obj.result = sanitize_data(current_result)
                        flag_modified(job_obj, "result")
                        await session.commit()
            except: pass
            await asyncio.sleep(3.0)

    async def stop_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["stop_requested"] = True
            self.job_states[job_id]["is_running"] = False
            print(f"🛑 [SWING] Stop Signal Received for {job_id}")

    async def pause_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = True
            print(f"⏸️ [SWING] Pause Signal Received for {job_id}")

    async def resume_job(self, job_id: str):
        if job_id in self.job_states:
            self.job_states[job_id]["pause_requested"] = False
            print(f"▶️ [SWING] Resume Signal Received for {job_id}")

swing_engine = SwingEngine()
