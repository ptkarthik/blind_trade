import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.swing_trade import SwingTrade

logger = logging.getLogger(__name__)

class TradeManager:
    """
    Trade Lifecycle Manager for Swing Trading.
    Tracks active trades, manages stop-loss updates, and archives trade history.
    """

    def __init__(self):
        self.active_trades: List[Dict[str, Any]] = []
        self.trade_history: List[Dict[str, Any]] = []
        self._initialized = False

    async def sync_from_db(self):
        """
        Loads all OPEN trades from the database into memory on startup.
        """
        async with AsyncSessionLocal() as session:
            try:
                # Load Open Trades
                stmt = select(SwingTrade).where(SwingTrade.status == "OPEN")
                result = await session.execute(stmt)
                db_trades = result.scalars().all()
                
                self.active_trades = []
                for t in db_trades:
                    # Convert SA Model to Dict for internal logic compatibility
                    self.active_trades.append(self._model_to_dict(t))
                
                # Load recent history (optional, for P&L tracking)
                hist_stmt = select(SwingTrade).where(SwingTrade.status == "CLOSED").limit(50)
                hist_result = await session.execute(hist_stmt)
                self.trade_history = [self._model_to_dict(t) for t in hist_result.scalars().all()]
                
                self._initialized = True
                logger.info(f"♻️ Trade Manager: Restored {len(self.active_trades)} active trades from DB.")
            except Exception as e:
                logger.error(f"❌ Failed to sync TradeManager from DB: {e}")

    def _model_to_dict(self, model: SwingTrade) -> Dict[str, Any]:
        """Helper to convert DB model to dictionary format used by services."""
        return {
            "id": model.id,
            "symbol": model.symbol,
            "strategy": model.strategy,
            "setup_type": model.setup_type,
            "entry": model.entry,
            "stop_loss": model.stop_loss,
            "initial_stop_loss": model.initial_stop_loss,
            "target": model.target,
            "quantity": model.quantity,
            "entry_date": model.entry_date.strftime("%Y-%m-%d %H:%M:%S") if model.entry_date else "",
            "status": model.status,
            "partial_exit_done": model.partial_exit_done,
            "sector": model.sector,
            "confidence": model.confidence
        }

    async def add_trade(self, trade: Dict[str, Any]):
        """
        Appends a newly executed trade to the active monitor.
        Expected structure: {symbol, strategy, entry, stop_loss, target, quantity, ...}
        """
        symbol = trade.get("symbol")
        
        # Ensure duplicate symbols are not added to active monitoring
        if any(t["symbol"] == symbol for t in self.active_trades):
            logger.warning(f"⚠️ Trade Manager: {symbol} is already an active trade.")
            return

        # Enrich trade with lifecycle metadata for DB
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        trade_entry = {
            "symbol": symbol,
            "strategy": trade.get("strategy_type", trade.get("strategy", "UNKNOWN")),
            "setup_type": trade.get("setup_type"),
            "entry": float(trade.get("entry", 0.0)),
            "stop_loss": float(trade.get("stop_loss", 0.0)),
            "initial_stop_loss": float(trade.get("stop_loss", 0.0)),
            "target": float(trade.get("target", 0.0)),
            "quantity": int(trade.get("quantity", 0)),
            "entry_date": trade.get("entry_date", now_str),
            "status": "OPEN",
            "partial_exit_done": bool(trade.get("partial_exit_done", False)),
            "sector": trade.get("sector"),
            "confidence": trade.get("confidence")
        }
        
        # Persist to Database
        async with AsyncSessionLocal() as session:
            try:
                db_trade = SwingTrade(
                    symbol=trade_entry["symbol"],
                    strategy=trade_entry["strategy"],
                    setup_type=trade_entry["setup_type"],
                    entry=trade_entry["entry"],
                    stop_loss=trade_entry["stop_loss"],
                    initial_stop_loss=trade_entry["initial_stop_loss"],
                    target=trade_entry["target"],
                    quantity=trade_entry["quantity"],
                    status=trade_entry["status"],
                    partial_exit_done=trade_entry["partial_exit_done"],
                    sector=trade_entry["sector"],
                    confidence=trade_entry["confidence"],
                    entry_date=datetime.strptime(trade_entry["entry_date"], "%Y-%m-%d %H:%M:%S")
                )
                session.add(db_trade)
                await session.commit()
                await session.refresh(db_trade)
                
                # Add the ID from DB
                trade_entry["id"] = db_trade.id
                self.active_trades.append(trade_entry)
                logger.info(f"🚀 Trade Manager: Monitoring started for {symbol} (Saved to DB).")
            except Exception as e:
                await session.rollback()
                logger.error(f"❌ Failed to persist new trade {symbol}: {e}")

    def get_active_trades(self) -> List[Dict[str, Any]]:
        """Returns all currently open trades."""
        return self.active_trades

    def get_trade_by_symbol(self, symbol: str) -> Dict[str, Any] | None:
        """Finds an active trade by its symbol."""
        return next((t for t in self.active_trades if t["symbol"] == symbol), None)

    async def update_trades(self, market_data: Dict[str, Any]):
        """
        Evaluates each active trade against the latest OHLC market data.
        Triggered daily or on demand.
        """
        # We use a list copy for safe iteration while closing trades
        for trade in list(self.active_trades):
            symbol = trade["symbol"]
            latest_ohlc = market_data.get(symbol)
            
            if not latest_ohlc:
                continue
            
            latest_price = latest_ohlc.get("close")
            if not latest_price:
                continue

            # 1. Stop Loss Protection (Global)
            if latest_price <= trade["stop_loss"]:
                await self.close_trade(symbol, latest_price, "STOP_LOSS")
                continue

            # 2. Strategy Specific Exit Logic
            if trade["strategy"] == "PULLBACK":
                # Pullbacks follow strict Target at 2.0R
                if latest_price >= trade["target"]:
                    await self.close_trade(symbol, latest_price, "TARGET_HIT")
                    continue
                
                # Break-Even Safety Net (1.0R)
                R = abs(trade["entry"] - trade["initial_stop_loss"])
                if latest_price >= (trade["entry"] + 1.0 * R):
                    new_be_sl = trade["entry"] + (0.1 * R)
                    if new_be_sl > trade["stop_loss"]:
                        trade["stop_loss"] = round(new_be_sl, 2)
                        logger.info(f"🛡️ PULLBACK BE DEFENSE: {symbol} hit 1.0R. SL moved to {trade['stop_loss']}.")
            
            elif trade["strategy"] == "BREAKOUT":
                # Breakouts use Hybrid Trailing Logic
                await self.manage_breakout_exit(trade, latest_ohlc)

            # 3. Time-Based Stops (Global)
            # Ensure capital isn't stuck in sideways trades
            from datetime import datetime
            current_date = datetime.utcnow()
            await self.enforce_time_stop(trade, current_date, latest_price)
            
            # 4. Sync Trailing Stop / Partial Exit to DB
            async with AsyncSessionLocal() as session:
                try:
                    await session.execute(
                        update(SwingTrade)
                        .where(SwingTrade.id == trade["id"])
                        .values(
                            stop_loss=trade["stop_loss"],
                            partial_exit_done=trade["partial_exit_done"],
                            quantity=trade["quantity"]
                        )
                    )
                    await session.commit()
                except Exception as e:
                    logger.error(f"❌ Failed to sync update for {symbol} to DB: {e}")

    async def enforce_time_stop(self, trade: Dict[str, Any], current_date: datetime, current_price: float):
        """
        Exits trades that are not moving with sufficient velocity.
        - Rules: 14-day Time Stop (<0.5R profit) or 21-day Max Duration.
        """
        from datetime import datetime
        try:
            entry_date = datetime.strptime(trade["entry_date"], "%Y-%m-%d %H:%M:%S")
            holding_days = (current_date - entry_date).days
            
            # Calculate Risk Unit (R)
            R = abs(trade["entry"] - trade["initial_stop_loss"])
            if R <= 0: R = 1.0 # Safety
            
            profit = current_price - trade["entry"]
            
            # Rule 1: Sideways Movement (7 Days)
            if holding_days >= 7 and profit < (0.5 * R):
                await self.close_trade(trade["symbol"], current_price, "TIME_STOP_7D")
                return # Already closed

            # Rule 2: Max Strategic Duration reached (21 Days)
            if holding_days >= 21:
                await self.close_trade(trade["symbol"], current_price, "MAX_DURATION_EXIT")
                
        except Exception as e:
            logger.error(f"❌ Error in time-based exit for {trade['symbol']}: {e}")

    async def manage_breakout_exit(self, trade: Dict[str, Any], latest_ohlc: Dict[str, Any]):
        """
        Handles specialized 'Hybrid Exit' for Momentum Breakouts:
        - Partial Exit at 1.5R: Sells 50%, protects entry (+0.5R)
        - Trail via EMA 9 afterwards: Lets winners run while locking in gains
        """
        current_price = latest_ohlc.get("close", 0)
        if current_price <= 0:
             return

        # 1. Calculate Risk Unit (R)
        entry = trade["entry"]
        initial_sl = trade["initial_stop_loss"]
        # In a long breakout, R is entry - initial_sl
        R = abs(entry - initial_sl)
        
        if R <= 0:
             return # Should not happen with valid trades

        # 1.5 Break-Even Safety Net (1.0R)
        if current_price >= (entry + 1.0 * R) and not trade.get("partial_exit_done"):
            new_be_sl = entry + (0.1 * R)
            if new_be_sl > trade.get("stop_loss", 0):
                trade["stop_loss"] = round(new_be_sl, 2)
                logger.info(f"🛡️ BREAKOUT BE DEFENSE: {trade['symbol']} hit 1.0R. SL moved to {trade['stop_loss']}.")

        # 2. Check for Partial Profit Booking (1.5R)
        target_1_5R = entry + (1.5 * R)
        
        if not trade.get("partial_exit_done") and current_price >= target_1_5R:
            # Book 50% Profit
            old_qty = trade["quantity"]
            new_qty = old_qty // 2
            trade["quantity"] = new_qty
            trade["partial_exit_done"] = True
            
            # Guarantee profit by moving SL to Entry + 0.5R (Floor)
            new_sl = max(entry + (0.5 * R), trade["stop_loss"])
            trade["stop_loss"] = round(new_sl, 2)
            
            logger.info(f"💰 PARTIAL PROFIT: {trade['symbol']} hit 1.5R (@{round(target_1_5R, 2)}). "
                        f"Sold 50%. New Qty: {new_qty}. SL protected at {trade['stop_loss']}.")

        # 3. Dynamic Trailing Stop (Post-Partial Exit)
        # V1.1 Swing Hardening: Anchor to T-1 (ema_9_prev) to avoid intraday whipsaws during volatility
        if trade.get("partial_exit_done"):
            ema_9_prev = latest_ohlc.get("ema_9_prev")
            if ema_9_prev:
                self.update_trailing_stop(trade, ema_9_prev)

    def update_trailing_stop(self, trade: Dict[str, Any], ema_value: float):
        """
        Dynamically moves the stop loss up as the trade goes in our favor.
        Ensures the stop loss NEVER decreases.
        """
        if not ema_value or ema_value <= 0:
            return

        old_sl = trade.get("stop_loss", 0)
        
        # 1. Breakout Logic (Aggressive Trailing post-partial exit)
        if trade["strategy"] == "BREAKOUT" and trade.get("partial_exit_done"):
            new_sl = max(old_sl, round(ema_value, 2))
            if new_sl > old_sl:
                trade["stop_loss"] = new_sl
                logger.info(f"🛰️ BREAKOUT TRAIL: {trade['symbol']} SL moved up to {new_sl} (EMA 9).")

        # 2. Pullback Logic (Conservative Trailing to protect larger gains)
        elif trade["strategy"] == "PULLBACK":
            # For pullbacks, we only trail once the trade is already well in profit (>1R)
            # This is optional/conservative trailing to avoid getting 'shaken out' early
            new_sl = max(old_sl, round(ema_value, 2))
            if new_sl > old_sl:
                 trade["stop_loss"] = new_sl
                 logger.info(f"🛰️ PULLBACK TRAIL: {trade['symbol']} SL moved up to {new_sl} (EMA 20).")

    async def calculate_today_pnl(self) -> float:
        """
        Calculates the total realized P&L for trades exited today from memory history.
        (Note: In future, this could query the DB for a wider time range).
        """
        from datetime import datetime
        today_str = datetime.utcnow().strftime("%Y-%m-%d")
        
        today_trades = [t for t in self.trade_history if t.get("exit_date", "").startswith(today_str)]
        return sum(t.get("pnl_amount", 0.0) for t in today_trades)

    async def check_daily_loss(self, total_capital: float) -> str:
        """
        Checks if today's net liquidation value (realized loss + unrealized drawdown) 
        has breached the 2% safety limit.
        """
        realized_pnl = await self.calculate_today_pnl()
        unrealized_pnl = 0.0
        
        # 1. Fetch current prices for active trades to calculate unrealized drawdown
        active_symbols = [t["symbol"] for t in self.active_trades]
        if active_symbols:
            from app.services.market_data import market_service
            live_data = await market_service.get_batch_prices(active_symbols)
            
            for trade in self.active_trades:
                sym = trade["symbol"]
                if sym in live_data:
                    current_price = live_data[sym].get("price", 0)
                    if current_price > 0:
                        position_pnl = (current_price - trade["entry"]) * trade["quantity"]
                        unrealized_pnl += position_pnl

        total_daily_drawdown = realized_pnl + unrealized_pnl
        
        if total_daily_drawdown < 0 and abs(total_daily_drawdown) >= (total_capital * 0.02):
            logger.warning(f"🛑 DAILY LOSS LIMIT BREACHED: Net Drawdown ({round(total_daily_drawdown, 2)} | Realized: {round(realized_pnl, 2)}, Unrealized: {round(unrealized_pnl, 2)}) "
                         f"is >= 2% of capital. STOP_TRADING initiated.")
            return "STOP_TRADING"
            
        return "CONTINUE"

    async def calculate_total_risk(self, total_capital: float) -> float:
        """
        Calculates total current portfolio risk as a % of capital.
        Risk = sum of (Entry - StopLoss) * Qty for all active positions.
        """
        if total_capital <= 0: return 0.0
        
        total_risk_amount = sum(
            abs(t["entry"] - t["stop_loss"]) * t["quantity"] 
            for t in self.active_trades
        )
        
        return (total_risk_amount / total_capital) * 100

    async def is_risk_limit_reached(self, total_capital: float) -> bool:
        """
        Returns True if total portfolio risk is >= 5%.
        """
        risk_pct = await self.calculate_total_risk(total_capital)
        if risk_pct >= 5.0:
            logger.warning(f"🛡️ PORTFOLIO RISK LIMIT: {round(risk_pct, 1)}% risk exposure. Blocking new trades.")
            return True
        return False

    async def close_trade(self, symbol: str, exit_price: float, reason: str = "TARGET_HIT"):
        """
        Moves an active trade to history and updates its final status.
        """
        trade = self.get_trade_by_symbol(symbol)
        if not trade:
            logger.error(f"❌ Trade Manager: Cannot close {symbol}. Position not found.")
            return

        # Calculate P&L and Performance Metrics
        initial_sl = trade.get("initial_stop_loss", trade["stop_loss"])
        R_unit = abs(trade["entry"] - initial_sl)
        
        # Risk-Adjusted Return (R-Multiple)
        r_multiple = (exit_price - trade["entry"]) / R_unit if R_unit > 0 else 0
        
        from datetime import datetime
        exit_date_obj = datetime.utcnow()
        entry_date_obj = datetime.strptime(trade["entry_date"], "%Y-%m-%d %H:%M:%S")
        holding_days = (exit_date_obj - entry_date_obj).days
        
        pnl = (exit_price - trade["entry"]) * trade["quantity"]
        pnl_pct = ((exit_price / trade["entry"]) - 1) * 100

        # Update Database
        async with AsyncSessionLocal() as session:
            try:
                stmt = update(SwingTrade).where(SwingTrade.id == trade["id"]).values(
                    exit_price=round(exit_price, 2),
                    exit_date=exit_date_obj,
                    exit_reason=reason,
                    status="CLOSED",
                    r_multiple=round(r_multiple, 2),
                    holding_days=holding_days,
                    pnl_amount=round(pnl, 2),
                    pnl_percentage=round(pnl_pct, 2)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(f"✅ Trade Manager: Persisted closure of {symbol} to DB.")
            except Exception as e:
                logger.error(f"❌ Failed to persist closure for {symbol}: {e}")

        # Update in-memory state
        trade.update({
            "exit_price": round(exit_price, 2),
            "exit_date": exit_date_obj.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "CLOSED",
            "close_reason": reason,
            "pnl_amount": round(pnl, 2),
            "pnl_percentage": round(pnl_pct, 2),
            "r_multiple": round(r_multiple, 2),
            "holding_days": holding_days
        })

        self.trade_history.append(trade)
        self.active_trades = [t for t in self.active_trades if t["symbol"] != symbol]
        
        # V1.1 Swing Hardening: Sync realized PnL back to Portfolio Engine NAV
        try:
            from app.services.portfolio_engine import portfolio_engine
            portfolio_engine.add_realized_pnl(pnl)
        except Exception as e:
            logger.error(f"Failed to sync NAV after closing {symbol}: {e}")
        
        logger.info(f"📉 Trade Manager: Closed {symbol} at {exit_price}. Reason: {reason}. "
                    f"P&L: {trade['pnl_percentage']}% | R-Multiple: {trade['r_multiple']}")

trade_manager = TradeManager()
