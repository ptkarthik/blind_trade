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
        Evaluates hold/sell logic and Dynamic Radar Scoring.
        Returns: (Action, Reason, NewStopLoss)
        """
        action = "HOLD"
        reason = "Trend intact."
        new_stop = trade.stop_loss

        # Radar Scoring Init
        radar_score = 50.0 # Neutral default
        profit_pct = ((current_price - trade.entry) / trade.entry) * 100
        
        # Track Max Profit Reached
        scan_data = trade.scan_data or {}
        max_profit_pct = scan_data.get("max_profit_pct", 0.0)
        if profit_pct > max_profit_pct:
            max_profit_pct = profit_pct
            scan_data["max_profit_pct"] = max_profit_pct
            trade.scan_data = scan_data

        # 1. Hard Stop Loss Hit
        if current_price <= trade.stop_loss:
            return "SELL", "Stop Loss Hit", new_stop

        # 2. Target Hit
        if current_price >= trade.target:
            return "SELL", "Target Reached", new_stop

        # 3. Dynamic Trailing Stop Logic (Multi-Tier)
        
        # Tier 3 (Aggressive Trailing for > 10% gains): Trail tightly by 3%
        if max_profit_pct >= 10.0:
            tier_3_stop = round(current_price * 0.97, 2)
            if tier_3_stop > new_stop:
                new_stop = tier_3_stop
                reason = "Tier 3 Trailing Stop (Locked Gains)"
                
        # Tier 2 (Gains Locking for > 5% gains): Lock in at least 2.5% below current, or breakeven+2.5%
        elif max_profit_pct >= 5.0:
            tier_2_stop = round(max(trade.entry * 1.025, current_price * 0.975), 2)
            if tier_2_stop > new_stop:
                new_stop = tier_2_stop
                reason = "Tier 2 Trailing Stop (Locked >2.5%)"
                
        # Tier 1 (Capital Protection for > 2.5% gains): Move to Entry + 0.5%
        elif max_profit_pct >= 2.5:
            breakeven_stop = round(trade.entry * 1.005, 2)
            if breakeven_stop > new_stop:
                new_stop = breakeven_stop
                reason = "Tier 1 Trailing Stop (Capital Protected)"

        # 4. Intraday Trend Analysis & Radar Scoring
        if df_15m is not None and not df_15m.empty and len(df_15m) > 20:
            try:
                from ta.trend import EMAIndicator
                from ta.momentum import RSIIndicator
                
                close_prices = df_15m['close']
                ema_20 = EMAIndicator(close=close_prices, window=20).ema_indicator().iloc[-1]
                rsi_14 = RSIIndicator(close=close_prices, window=14).rsi().iloc[-1]
                
                # Base score based on profit
                radar_score = 50.0 + (profit_pct * 2)
                
                # Bonus for being above 15m EMA
                if current_price > ema_20:
                    radar_score += 15
                else:
                    radar_score -= 20
                    
                # Overbought/Oversold modifiers
                if rsi_14 > 70:
                    radar_score += 10 # Strong momentum
                elif rsi_14 < 40:
                    radar_score -= 15 # Weakening
                    
                # Early Exit / Predictive Sell logic
                # If we are nicely profitable but suddenly collapse below EMA and RSI is dying
                if profit_pct > 3.0 and current_price < ema_20 and rsi_14 < 45:
                    aggressive_stop = round(ema_20 * 0.995, 2)
                    if aggressive_stop > new_stop and current_price > aggressive_stop:
                        new_stop = aggressive_stop
                        reason = "Radar: Bearish Divergence detected, tightening stop."
                        
                trade.current_score = round(max(0, min(100, radar_score)), 1)
                
            except Exception as e:
                pass
        else:
            trade.current_score = round(max(0, min(100, 50.0 + (profit_pct * 2))), 1)

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
                        "created_at": t.created_at.isoformat() if t.created_at else t.entry_date.isoformat(),
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
                    # Deep continuous scan (Decoupled from fresh entry criteria)
                    analysis = await swing_engine.evaluate_active_position(trade.symbol, trade.strategy)
                    if analysis and "score" in analysis:
                        trade.current_score = float(analysis["score"])
                        trade.scan_data = analysis
                    else:
                        trade.current_score = 50.0 # Neutral fallback if data fetch completely fails
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
