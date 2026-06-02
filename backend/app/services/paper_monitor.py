import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.papertrade import PaperTrade, Account
from app.services.market_data import market_service
from app.services.intraday_engine import intraday_engine # [V24 FIX #8]

logger = logging.getLogger(__name__)

class PaperMonitor:
    """
    Automated Monitor for Intraday Paper Trades.
    - Checks for Stop Loss (SL) and Target (TP) breaches.
    - Handles EOD (End of Day) automated square-off at 3:15 PM IST.
    - NEW: Handles 'Morning Reset' to clear stale trades from previous days.
    """
    
    def __init__(self):
        self.is_running = False

    def get_ist_now(self):
        """Helper to get current time in IST (UTC+5:30)."""
        # IST is UTC+5:30
        return datetime.now(timezone(timedelta(hours=5, minutes=30)))

    async def check_trades(self):
        """
        Main logic loop to monitor open positions.
        - Optimized to use Batch Price fetching (Phase 102).
        - [AUDIT GAP-2] Daily P&L Circuit Breaker prevents catastrophic loss days.
        """
        async with AsyncSessionLocal() as session:
            try:
                # [AUDIT GAP-2] DAILY P&L CIRCUIT BREAKER
                # If today's realized losses exceed -2% of capital, stop active management.
                # Positions will still hit their hard SL/TP but no trailing/advanced exits.
                ist_now = self.get_ist_now()
                today_start_utc = (ist_now.replace(hour=0, minute=0, second=0, microsecond=0) 
                                   - (ist_now.utcoffset() or __import__('datetime').timedelta(0)))
                
                from sqlalchemy import func, case, and_
                daily_pnl_query = select(
                    func.coalesce(func.sum(
                        case(
                            (and_(PaperTrade.target != None, PaperTrade.target < PaperTrade.buy_price),
                             (PaperTrade.buy_price - PaperTrade.sell_price) * PaperTrade.qty),
                            else_=(PaperTrade.sell_price - PaperTrade.buy_price) * PaperTrade.qty
                        )
                    ), 0)
                ).where(
                    PaperTrade.status == "CLOSED",
                    PaperTrade.sell_time >= today_start_utc.replace(tzinfo=None)
                )
                daily_pnl_result = await session.execute(daily_pnl_query)
                today_pnl = float(daily_pnl_result.scalar() or 0)
                
                CIRCUIT_BREAKER_CAPITAL = 1000000.0  # ₹10L base
                CIRCUIT_BREAKER_PCT = 0.02           # -2% daily max loss
                
                if today_pnl < -(CIRCUIT_BREAKER_CAPITAL * CIRCUIT_BREAKER_PCT):
                    if not getattr(self, '_circuit_breaker_logged', False):
                        logger.warning(f" [CIRCUIT BREAKER] Daily loss ₹{today_pnl:,.0f} exceeds "
                                      f"-{CIRCUIT_BREAKER_PCT*100}% threshold. "
                                      f"Active position management SUSPENDED for today.")
                        self._circuit_breaker_logged = True
                    return  # Let positions hit natural SL/TP
                else:
                    self._circuit_breaker_logged = False
                
                # 1. Get all OPEN trades
                result = await session.execute(
                    select(PaperTrade).where(PaperTrade.status == "OPEN")
                )
                open_trades = result.scalars().all()
                
                if not open_trades:
                    return

                # 2. Market Timing (IST Based)
                ist_now = self.get_ist_now()
                today_ist_date = ist_now.date()
                
                # EOD Window: >= 3:15 PM IST
                is_eod_time = ist_now.hour > 15 or (ist_now.hour == 15 and ist_now.minute >= 15)
                
                # 3. Batch Fetch Prices for all active symbols (Phase 102)
                symbols = list(set([t.symbol for t in open_trades]))
                live_prices = {}
                try:
                    # Timeout to ensure monitor doesn't hang if provider is slow
                    live_prices = await asyncio.wait_for(market_service.get_batch_prices(symbols), timeout=10.0)
                except Exception as e:
                    logger.error(f"Failed to batch fetch for monitor: {e}")
                    
                # 3.5 Concurrent Fetch for OHLC Data (Fix Execution Latency)
                async def fetch_ohlc(sym):
                    try:
                        return sym, await asyncio.wait_for(market_service.get_ohlc(sym, period="2d", interval="15m"), timeout=5.0)
                    except Exception:
                        return sym, None
                
                ohlc_tasks = [fetch_ohlc(sym) for sym in symbols]
                ohlc_results = await asyncio.gather(*ohlc_tasks)
                ohlc_data = {sym: df for sym, df in ohlc_results if df is not None}

                for trade in open_trades:
                    try:
                        # Convert trade buy_time (stored as UTC) to IST for comparison
                        # buy_time might be naive UTC, so we localize it
                        buy_time_ist = trade.buy_time.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
                        trade_ist_date = buy_time_ist.date()
                        
                        # STALE CHECK: Is this an MIS trade from 'Yesterday' (or older)?
                        is_stale_trade = trade.product_type == "MIS" and trade_ist_date < today_ist_date

                        # Extract price safely (Handle both dict and float for robustness)
                        price_data = live_prices.get(trade.symbol)
                        current_price = 0.0
                        
                        if isinstance(price_data, dict):
                            current_price = price_data.get("price", 0.0)
                        elif isinstance(price_data, (int, float)):
                            current_price = float(price_data)

                        if current_price == 0:
                            # Final fallback: individual fetch if batch failed
                            try:
                                data = await market_service.get_latest_price(trade.symbol)
                                current_price = data.get("price", 0.0) if isinstance(data, dict) else data
                            except: pass

                        if current_price == 0:
                            # If we STILL have no price AND trade is stale, force close with buy_price
                            if is_stale_trade:
                                current_price = trade.buy_price # Fallback to prevent hang
                            else:
                                continue

                        close_it = False
                        reason = "MANUAL"

                        # 1. MORNING RESET / STALE PURGE
                        if is_stale_trade:
                            close_it = True
                            reason = "EOD_RESET" # Purged as yesterday's leftover
                            logger.info(f" [PAPER] {trade.symbol} Stale Position (from {trade_ist_date}) purged at {current_price}")

                        # 2. ADVANCED EXIT EVALUATION (V24 FIX #8)
                        # Instead of just basic SL/TP, use the engine's evaluate_exit
                        elif not is_eod_time:
                            # Dynamic inference of Short constraints
                            is_short_pos = True if (trade.target and trade.buy_price and trade.target < trade.buy_price) else False
                            
                            try:
                                df_15m = ohlc_data.get(trade.symbol)
                                if df_15m is None:
                                    raise ValueError(f"Failed to fetch 15m OHLC for {trade.symbol}")
                                    
                                exit_eval = await intraday_engine.evaluate_exit(
                                    sym=trade.symbol,
                                    entry_price=trade.buy_price,
                                    stop_loss=trade.stop_loss,
                                    target=trade.target,
                                    df_15m=df_15m,
                                    entry_time=trade.buy_time,
                                    is_short=is_short_pos
                                )
                                
                                if exit_eval["action"] == "EXIT":
                                    close_it = True
                                    reason = exit_eval.get("reason", "Advanced Exit Signal")
                                    logger.info(f" [PAPER] {trade.symbol} Advanced Exit: {reason}")
                                elif exit_eval["action"] == "PARTIAL_EXIT":
                                    # [V40 GAP#6 FIX] Book 50% profit, trail remainder to breakeven
                                    exit_qty = max(1, trade.qty // 2)
                                    remaining_qty = trade.qty - exit_qty
                                    if remaining_qty > 0:
                                        await self._partial_close(session, trade, current_price, exit_qty, exit_eval.get("reason", "Partial Target"))
                                        trade.qty = remaining_qty
                                        new_stop = exit_eval.get("new_stop", trade.buy_price)
                                        if new_stop:
                                            trade.stop_loss = new_stop
                                        new_target = exit_eval.get("new_target")
                                        if new_target:
                                            trade.target = new_target
                                        logger.info(f" [PAPER] {trade.symbol} Partial: {exit_qty} sold, {remaining_qty} remain, SL→{trade.stop_loss}")
                                    else:
                                        close_it = True
                                        reason = exit_eval.get("reason", "Partial (full close)")
                                elif exit_eval["action"] == "TRAIL_STOP":
                                    new_stop = exit_eval.get("new_stop")
                                    if new_stop:
                                        # Protect trail update validity based on direction
                                        valid_trail = (new_stop < trade.stop_loss) if is_short_pos else (new_stop > trade.stop_loss)
                                        if valid_trail:
                                            trade.stop_loss = new_stop
                                            logger.info(f"️ [PAPER] {trade.symbol} Trailing Stop updated to {new_stop}")
                            except Exception as e:
                                logger.error(f"Advanced Exit Eval Failed for {trade.symbol}: {e}")
                                # Fallback to basic SL/TP if data fetch fails
                                if trade.stop_loss:
                                    sl_hit = current_price >= trade.stop_loss if is_short_pos else current_price <= trade.stop_loss
                                    if sl_hit:
                                        close_it = True
                                        reason = "STOP_LOSS"
                                        logger.info(f" [PAPER] {trade.symbol} SL hit at {current_price} (SL: {trade.stop_loss})")
                                if not close_it and trade.target:
                                    tgt_hit = current_price <= trade.target if is_short_pos else current_price >= trade.target
                                    if tgt_hit:
                                        close_it = True
                                        reason = "TARGET"
                                        logger.info(f" [PAPER] {trade.symbol} Target hit at {current_price} (Tgt: {trade.target})")

                        # 3. EOD EXIT (Late Afternoon)
                        elif is_eod_time and trade.product_type == "MIS":
                            close_it = True
                            reason = "EOD"
                            logger.info(f" [PAPER] {trade.symbol} EOD Square-off at {current_price}")

                        if close_it:
                            await self._close_trade(session, trade, current_price, reason)
                            
                    except Exception as e:
                        logger.error(f"Error monitoring {trade.symbol}: {e}")

                await session.commit()
            except Exception as e:
                logger.error(f"Monitor Loop Error: {e}")

    async def _partial_close(self, session, trade, price, exit_qty, reason):
        """
        [V40 GAP#6] Books profit on partial quantity without closing the full trade.
        Applies slippage and updates account P&L for the partial exit.
        """
        is_short = True if (trade.target and trade.buy_price and trade.target < trade.buy_price) else False
        _exit_slip = price * 0.0012  # Same slippage as full close
        exit_price = round(price + _exit_slip if is_short else price - _exit_slip, 2)
        
        if is_short:
            pnl = (trade.buy_price - exit_price) * exit_qty
        else:
            pnl = (exit_price - trade.buy_price) * exit_qty
        
        # Update account P&L for partial
        acc_res = await session.execute(select(Account).limit(1))
        account = acc_res.scalars().first()
        if account:
            partial_proceeds = exit_qty * exit_price if not is_short else (exit_qty * trade.buy_price + pnl)
            account.balance += partial_proceeds
            account.total_pnl += pnl
        
        logger.info(f" [PAPER] {trade.symbol} Partial Close ({reason}): {exit_qty} units at {exit_price}, P&L: {round(pnl, 2)}")

    async def _close_trade(self, session, trade, price, reason):
        """
        Internal helper to execute the paper trade closure.
        """
        # 1. Update Trade (with realistic exit slippage)
        # [V40 GAP#5 FIX] Apply 0.12% adverse slippage on exits (NSE mid-cap calibrated)
        is_short_pos = True if (trade.target and trade.buy_price and trade.target < trade.buy_price) else False
        _exit_slip = price * 0.0012
        trade.sell_price = round(price + _exit_slip if is_short_pos else price - _exit_slip, 2)
        trade.sell_time = datetime.utcnow() # Internal DB storage remains UTC for generic compatibility
        trade.status = "CLOSED"
        trade.close_reason = reason
        
        # 2. Update Account
        acc_res = await session.execute(select(Account).limit(1))
        account = acc_res.scalars().first()
        
        if account:
            is_short_log = True if (trade.target and trade.buy_price and trade.target < trade.buy_price) else False
            
            if is_short_log:
                pnl = (trade.buy_price - trade.sell_price) * trade.qty
                proceeds = (trade.buy_price * trade.qty) + pnl
            else:
                proceeds = trade.qty * trade.sell_price
                pnl = proceeds - (trade.qty * trade.buy_price)
            
            account.balance += proceeds
            account.total_pnl += pnl
            logger.info(f" [PAPER] {trade.symbol} Closed ({reason}). P&L: {round(pnl, 2)}")

paper_monitor = PaperMonitor()
