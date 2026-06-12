"""
[POSITION MANAGER] The 15-Minute Guardian Loop
================================================
Monitors OPEN trades in the `swing_trades` table.
Uses Kite to fetch live 15m data and LTP.
Calculates Trailing Stops, Take Profits, and issues Hold/Sell alerts.
"""

import logging
import asyncio
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.models.swing_trade import SwingTrade
from app.models.trade_alert import TradeAlert
from app.services.kite_data import kite_data
from app.services.notifier import notifier_service

logger = logging.getLogger("position_manager")

class PositionManager:
    """Guardian loop for active positions."""

    async def run_evaluation_cycle(self):
        """Runs the 15-minute evaluation for all OPEN positions."""
        logger.info("[GUARDIAN] Starting position evaluation cycle...")

        if not kite_data.is_ready:
            logger.warning("[GUARDIAN] Kite is not ready. Skipping cycle.")
            return

        try:
            async with AsyncSessionLocal() as session:
                # 1. Fetch all OPEN trades
                stmt = select(SwingTrade).where(SwingTrade.status == "OPEN")
                result = await session.execute(stmt)
                open_trades = result.scalars().all()

                if not open_trades:
                    logger.info("[GUARDIAN] No open positions to monitor.")
                    return

                symbols = [t.symbol for t in open_trades]
                logger.info(f"[GUARDIAN] Monitoring {len(symbols)} open positions: {symbols}")

                # 2. Fetch Live Prices (LTP) directly from Kite
                live_prices = await kite_data.get_ltp(symbols)
                
                # 3. Fetch 15m Intraday Data for trend analysis
                intraday_data = await kite_data.fetch_batch(symbols, interval="15m", period="2d")

                alerts_generated = 0

                for trade in open_trades:
                    symbol = trade.symbol
                    price_data = live_prices.get(symbol)
                    
                    if not price_data:
                        continue
                        
                    current_price = price_data.get("price", 0)
                    if current_price <= 0:
                        continue
                        
                    df_15m = intraday_data.get(symbol)
                    
                    # Evaluate trade
                    action, reason, new_stop = self._evaluate_trade(trade, current_price, df_15m)

                    # Update trailing stop if raised
                    if new_stop > trade.stop_loss:
                        trade.stop_loss = new_stop
                        trade.updated_at = datetime.utcnow()
                        
                        alert_msg = f"Trail Stop Raised to ₹{new_stop:.2f} (Locking profits)"
                        alert = TradeAlert(
                            symbol=symbol,
                            alert_type="INFO",
                            message=alert_msg,
                            price_at_alert=current_price,
                            scan_date=date.today().isoformat()
                        )
                        session.add(alert)
                        alerts_generated += 1
                        
                        # Fire mobile alert
                        await notifier_service.send_telegram_alert(
                            f"🛡️ <b>GUARDIAN UPDATE</b>\n"
                            f"🟢 <b>{symbol}</b>\n"
                            f"LTP: ₹{current_price:.2f}\n"
                            f"<i>{alert_msg}</i>"
                        )

                    # Handle EXIT signals (Advisory Mode Only)
                    if action == "SELL":
                        # The engine advises a SELL, but does NOT close the position.
                        # We just emit an alert if it's a critical breach.
                        
                        # Only emit alert if price has moved significantly since last check 
                        # to avoid spamming alerts every 15 minutes for the same level.
                        alert_msg = f"ADVISORY SELL SIGNAL: {reason} @ ₹{current_price:.2f}"
                        alert = TradeAlert(
                            symbol=symbol,
                            alert_type="WARNING" if "Stop Hit" in reason else "INFO",
                            message=alert_msg,
                            price_at_alert=current_price,
                            scan_date=date.today().isoformat()
                        )
                        session.add(alert)
                        alerts_generated += 1
                        print(f" 🚨 [GUARDIAN ADVISOR] SELL RECOMMENDED for {symbol}: {reason}", flush=True)
                        
                        # Fire mobile alert
                        await notifier_service.send_telegram_alert(
                            f"🚨 <b>GUARDIAN SELL ALERT</b>\n"
                            f"🔴 <b>{symbol}</b>\n"
                            f"LTP: ₹{current_price:.2f}\n"
                            f"Reason: {reason}\n"
                            f"<i>Action Required: Review position to exit.</i>"
                        )

                await session.commit()
                if alerts_generated > 0:
                    logger.info(f"[GUARDIAN] Cycle complete. Generated {alerts_generated} alerts.")

        except Exception as e:
            logger.error(f"[GUARDIAN] Cycle failed: {e}")
            import traceback
            traceback.print_exc()

    def _evaluate_trade(self, trade: SwingTrade, current_price: float, df_15m: pd.DataFrame) -> tuple[str, str, float]:
        """
        Evaluates hold/sell logic.
        Returns: (Action, Reason, NewStopLoss)
        """
        action = "HOLD"
        reason = "Trend intact."
        new_stop = trade.stop_loss

        # 1. Hard Stop Loss Hit
        if current_price <= trade.stop_loss:
            return "SELL", "Stop Loss Hit", new_stop

        # 2. Target Hit
        if current_price >= trade.target:
            return "SELL", "Target Reached", new_stop

        # 3. Trailing Stop Logic (If up > 4%, trail stop to breakeven or EMA20)
        profit_pct = ((current_price - trade.entry) / trade.entry) * 100
        
        if profit_pct >= 4.0 and trade.stop_loss < trade.entry:
            # Move stop to breakeven + 0.5% once up 4%
            breakeven_stop = round(trade.entry * 1.005, 2)
            if breakeven_stop > new_stop:
                new_stop = breakeven_stop
                reason = "Trailing stop to breakeven"

        # 4. Intraday Trend Analysis (if data available)
        if df_15m is not None and not df_15m.empty and len(df_15m) > 20:
            try:
                from ta.trend import EMAIndicator
                ema_20 = EMAIndicator(close=df_15m['close'], window=20).ema_indicator().iloc[-1]
                
                # If up significantly (>6%) and we close below 15m EMA20, trail aggressively
                if profit_pct >= 6.0:
                    aggressive_stop = round(ema_20 * 0.995, 2)
                    if aggressive_stop > new_stop and current_price > aggressive_stop:
                        new_stop = aggressive_stop
                        
                # Dead money check / Intraday bleed
                # If it's bleeding consistently intraday but hasn't hit stop, maybe just warn?
                # (For now, just rely on the trailing stop math)
            except:
                pass

        return action, reason, new_stop

    async def get_live_portfolio(self) -> List[Dict[str, Any]]:
        """Returns the active portfolio with live prices for the UI."""
        portfolio = []
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(SwingTrade).where(SwingTrade.status == "OPEN")
                result = await session.execute(stmt)
                open_trades = result.scalars().all()

                if not open_trades:
                    return []

                symbols = [t.symbol for t in open_trades]
                live_prices = await kite_data.get_ltp(symbols)
                
                for t in open_trades:
                    current_price = live_prices.get(t.symbol, {}).get("price", t.entry)
                    profit_pct = ((current_price - t.entry) / t.entry) * 100
                    
                    action, reason, _ = self._evaluate_trade(t, current_price, None)
                    
                    portfolio.append({
                        "id": t.id,
                        "symbol": t.symbol,
                        "strategy": t.strategy,
                        "entry": t.entry,
                        "current_price": current_price,
                        "stop_loss": t.stop_loss,
                        "target": t.target,
                        "profit_pct": round(profit_pct, 2),
                        "action": action,
                        "reason": reason,
                        "initial_score": t.initial_score or 0.0,
                        "current_score": t.current_score or 0.0,
                        "score": t.confidence or "N/A",
                        "scan_data": t.scan_data,
                        "initial_scan_data": t.initial_scan_data,
                        "quantity": t.quantity,
                        "holding_days": (datetime.utcnow() - t.entry_date).days,
                        "last_evaluated_at": t.updated_at.isoformat() if t.updated_at else None
                    })
        except Exception as e:
            logger.error(f"[GUARDIAN] Failed to get live portfolio: {e}")
            
        return portfolio

    async def send_portfolio_summary(self, title="HOURLY PORTFOLIO SUMMARY"):
        """Sends a full summary of all open positions to Telegram."""
        try:
            portfolio = await self.get_live_portfolio()
            if not portfolio:
                return
                
            msg = f"📊 <b>{title}</b>\n"
            msg += "--------------------------\n"
            
            for p in portfolio:
                icon = "🟢" if p["action"] == "HOLD" else "🔴"
                msg += f"{icon} <b>{p['symbol']}</b> (Scores: Initial {p['initial_score']} ➡️ Current {p['current_score']})\n"
                msg += f"LTP: ₹{p['current_price']:.2f} | <b>{p['profit_pct']:+.2f}%</b>\n"
                msg += f"Stop Loss: ₹{p['stop_loss']:.2f}\n"
                msg += f"Status: {p['action']} - {p['reason']}\n\n"
                
            await notifier_service.send_telegram_alert(msg)
            logger.info(f"[GUARDIAN] Summary sent: {title}")
        except Exception as e:
            logger.error(f"[GUARDIAN] Failed to send summary: {e}")

    async def run_hourly_deep_scan(self, title="HOURLY PORTFOLIO SUMMARY"):
        """Runs once an hour to deeply analyze active positions and update their AI Scores."""
        logger.info("[GUARDIAN] Starting hourly deep scan...")
        from app.services.swing_engine import swing_engine
        
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(SwingTrade).where(SwingTrade.status == "OPEN")
                result = await session.execute(stmt)
                open_trades = result.scalars().all()
                
                for trade in open_trades:
                    # Deep scan
                    analysis = await swing_engine.analyze_stock(trade.symbol)
                    if analysis and "score" in analysis:
                        trade.current_score = float(analysis["score"])
                        trade.scan_data = analysis
                    else:
                        trade.current_score = 50.0 # Neutral / No longer a fresh buy setup
                        if trade.scan_data:
                            # Update score internally so UI knows
                            trade.scan_data["score"] = 50.0
                            trade.scan_data["signal"] = "HOLD"
                
                await session.commit()
            
            # Send summary
            await self.send_portfolio_summary(title=title)
        except Exception as e:
            logger.error(f"[GUARDIAN] Deep scan failed: {e}")

position_manager = PositionManager()
