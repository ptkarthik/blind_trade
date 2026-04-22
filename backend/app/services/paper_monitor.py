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
        """
        async with AsyncSessionLocal() as session:
            try:
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
                            logger.info(f"🧹 [PAPER] {trade.symbol} Stale Position (from {trade_ist_date}) purged at {current_price}")

                        # 2. ADVANCED EXIT EVALUATION (V24 FIX #8)
                        # Instead of just basic SL/TP, use the engine's evaluate_exit for trailing stops, time decay, and structural breakdown
                        elif not is_eod_time:
                            # Fetch 15m data required for advanced evaluation
                            try:
                                df_15m = await asyncio.wait_for(market_service.get_ohlc(trade.symbol, period="2d", interval="15m"), timeout=5.0)
                                exit_eval = await intraday_engine.evaluate_exit(
                                    sym=trade.symbol,
                                    entry_price=trade.buy_price,
                                    stop_loss=trade.stop_loss,
                                    target=trade.target,
                                    df_15m=df_15m,
                                    entry_time=trade.buy_time
                                )
                                
                                if exit_eval["action"] in ["EXIT", "PARTIAL_EXIT"]:
                                    close_it = True
                                    reason = exit_eval.get("reason", "Advanced Exit Signal")
                                    logger.info(f"🧠 [PAPER] {trade.symbol} Advanced Exit: {reason}")
                                elif exit_eval["action"] == "TRAIL_STOP":
                                    new_stop = exit_eval.get("new_stop")
                                    if new_stop and new_stop > trade.stop_loss:
                                        trade.stop_loss = new_stop
                                        logger.info(f"🛡️ [PAPER] {trade.symbol} Trailing Stop updated to {new_stop}")
                            except Exception as e:
                                logger.error(f"Advanced Exit Eval Failed for {trade.symbol}: {e}")
                                # Fallback to basic SL/TP if data fetch fails
                                if trade.stop_loss and current_price <= trade.stop_loss:
                                    close_it = True
                                    reason = "STOP_LOSS"
                                    logger.info(f"🚨 [PAPER] {trade.symbol} SL hit at {current_price} (SL: {trade.stop_loss})")
                                elif trade.target and current_price >= trade.target:
                                    close_it = True
                                    reason = "TARGET"
                                    logger.info(f"🎯 [PAPER] {trade.symbol} Target hit at {current_price} (Tgt: {trade.target})")

                        # 3. EOD EXIT (Late Afternoon)
                        elif is_eod_time and trade.product_type == "MIS":
                            close_it = True
                            reason = "EOD"
                            logger.info(f"🕒 [PAPER] {trade.symbol} EOD Square-off at {current_price}")

                        if close_it:
                            await self._close_trade(session, trade, current_price, reason)
                            
                    except Exception as e:
                        logger.error(f"Error monitoring {trade.symbol}: {e}")

                await session.commit()
            except Exception as e:
                logger.error(f"Monitor Loop Error: {e}")

    async def _close_trade(self, session, trade, price, reason):
        """
        Internal helper to execute the paper trade closure.
        """
        # 1. Update Trade
        trade.sell_price = price
        trade.sell_time = datetime.utcnow() # Internal DB storage remains UTC for generic compatibility
        trade.status = "CLOSED"
        trade.close_reason = reason
        
        # 2. Update Account
        acc_res = await session.execute(select(Account).limit(1))
        account = acc_res.scalars().first()
        
        if account:
            # We assume long positions for now as per PaperTrade model triggers
            proceeds = trade.qty * price
            pnl = proceeds - (trade.qty * trade.buy_price)
            
            account.balance += proceeds
            account.total_pnl += pnl
            logger.info(f"✅ [PAPER] {trade.symbol} Closed ({reason}). P&L: {round(pnl, 2)}")

paper_monitor = PaperMonitor()
