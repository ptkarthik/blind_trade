"""
[POSITION MANAGER] The Dynamic Guardian Radar v2
=================================================
Monitors OPEN trades in the `swing_trades` table.
Uses Kite to fetch live 15m + Daily data and LTP.
Calculates Trailing Stops, Radar Scores, Dead Money flags,
Volume Health, Nifty Regime, and issues Hold/Sell alerts.
"""

import logging
import asyncio
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.models.swing_trade import SwingTrade
from app.models.trade_alert import TradeAlert
from app.services.kite_data import kite_data
from app.services.notifier import notifier_service

logger = logging.getLogger("position_manager")

# Nifty 50 symbol for market regime detection
NIFTY_SYMBOL = "NIFTY 50.NS"


class PositionManager:
    """Guardian Radar v2 for active positions."""

    def __init__(self):
        self._nifty_regime = "NEUTRAL"  # BULLISH / NEUTRAL / BEARISH
        self._nifty_change_pct = 0.0

    # =========================================================================
    # MARKET REGIME (Nifty 50 Health Check)
    # =========================================================================
    async def _update_nifty_regime(self):
        """Fetch Nifty 50 daily data and determine broad market regime."""
        try:
            nifty_data = await kite_data.fetch_batch(
                [NIFTY_SYMBOL], interval="1d", period="10d"
            )
            df = nifty_data.get(NIFTY_SYMBOL)
            if df is None or df.empty or len(df) < 3:
                self._nifty_regime = "NEUTRAL"
                self._nifty_change_pct = 0.0
                return

            # Today's change
            today_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            self._nifty_change_pct = ((today_close - prev_close) / prev_close) * 100

            # 3-day trend
            three_day_change = ((today_close - df['close'].iloc[-3]) / df['close'].iloc[-3]) * 100

            if self._nifty_change_pct < -1.5 or three_day_change < -3.0:
                self._nifty_regime = "BEARISH"
            elif self._nifty_change_pct > 1.0 and three_day_change > 1.5:
                self._nifty_regime = "BULLISH"
            else:
                self._nifty_regime = "NEUTRAL"

            logger.info(
                f"[GUARDIAN] Nifty Regime: {self._nifty_regime} "
                f"(Today: {self._nifty_change_pct:+.2f}%, 3D: {three_day_change:+.2f}%)"
            )
        except Exception as e:
            logger.warning(f"[GUARDIAN] Nifty regime check failed: {e}")
            self._nifty_regime = "NEUTRAL"
            self._nifty_change_pct = 0.0

    # =========================================================================
    # VOLUME HEALTH SCORING
    # =========================================================================
    def _score_volume_health(self, df: pd.DataFrame) -> tuple[float, str]:
        """
        Analyze volume patterns.
        Returns (score_modifier, description).
        Positive = healthy volume, Negative = volume warning.
        """
        if df is None or df.empty or 'volume' not in df.columns or len(df) < 10:
            return 0.0, "Volume data unavailable"

        try:
            volumes = df['volume'].values
            closes = df['close'].values

            # Average volume (last 10 bars)
            avg_vol = np.mean(volumes[-10:])
            recent_vol = np.mean(volumes[-3:])

            if avg_vol <= 0:
                return 0.0, "Zero volume"

            vol_ratio = recent_vol / avg_vol

            # Check if price is rising on declining volume (distribution)
            price_rising = closes[-1] > closes[-5] if len(closes) >= 5 else False
            price_falling = closes[-1] < closes[-5] if len(closes) >= 5 else False

            score = 0.0
            desc = ""

            if price_rising and vol_ratio < 0.6:
                # Rising price + dying volume = DISTRIBUTION (very bad)
                score = -20.0
                desc = "Distribution: Price rising on declining volume"
            elif price_falling and vol_ratio > 1.5:
                # Falling price + surging volume = PANIC SELLING (very bad)
                score = -25.0
                desc = "Panic selling: Heavy volume on decline"
            elif price_rising and vol_ratio > 1.3:
                # Rising price + strong volume = ACCUMULATION (very good)
                score = +15.0
                desc = "Accumulation: Strong volume confirms rally"
            elif vol_ratio < 0.5:
                # Volume drying up = dead money
                score = -10.0
                desc = "Volume drying up: Low conviction"
            else:
                score = 0.0
                desc = "Volume normal"

            return score, desc
        except Exception:
            return 0.0, "Volume analysis error"

    # =========================================================================
    # DEAD MONEY DETECTION
    # =========================================================================
    def _check_dead_money(self, trade: SwingTrade, df_daily: pd.DataFrame) -> tuple[bool, str]:
        """
        Detects if a stock has been going sideways with no meaningful movement.
        Returns (is_dead_money, reason).
        """
        holding_days = (datetime.utcnow() - trade.entry_date).days
        profit_pct = 0.0
        if trade.entry > 0:
            # Use current scan_data to get latest price info
            scan_data = trade.scan_data or {}
            max_profit = scan_data.get("max_profit_pct", 0.0)
            profit_pct = max_profit

        # If held > 10 days and never exceeded 2% gain, it's dead money
        if holding_days >= 10 and profit_pct < 2.0:
            return True, f"Dead Money: Held {holding_days} days, max gain only {profit_pct:.1f}%"

        # Check daily range compression (if daily data available)
        if df_daily is not None and not df_daily.empty and len(df_daily) >= 5:
            try:
                last_5_highs = df_daily['high'].iloc[-5:].values
                last_5_lows = df_daily['low'].iloc[-5:].values
                daily_ranges = ((last_5_highs - last_5_lows) / last_5_lows) * 100
                avg_range = np.mean(daily_ranges)

                if avg_range < 1.0 and holding_days >= 7:
                    return True, f"Dead Money: Avg daily range only {avg_range:.1f}% over 5 days"
            except Exception:
                pass

        return False, ""

    # =========================================================================
    # MAIN EVALUATION CYCLE
    # =========================================================================
    async def run_evaluation_cycle(self):
        """Runs the evaluation for all OPEN positions with full radar analysis."""
        logger.info("[GUARDIAN v2] Starting position evaluation cycle...")

        if not kite_data.is_ready:
            logger.warning("[GUARDIAN v2] Kite is not ready. Skipping cycle.")
            return

        try:
            # Step 0: Check Nifty regime FIRST
            await self._update_nifty_regime()

            async with AsyncSessionLocal() as session:
                # 1. Fetch all OPEN trades
                stmt = select(SwingTrade).where(SwingTrade.status == "OPEN")
                result = await session.execute(stmt)
                open_trades = result.scalars().all()

                if not open_trades:
                    logger.info("[GUARDIAN v2] No open positions to monitor.")
                    return

                symbols = [t.symbol for t in open_trades]
                logger.info(f"[GUARDIAN v2] Monitoring {len(symbols)} open positions: {symbols}")

                # 2. Fetch Live Prices (LTP)
                live_prices = await kite_data.get_ltp(symbols)

                # 3. Fetch 15m Intraday Data for trend analysis
                intraday_data = await kite_data.fetch_batch(symbols, interval="15m", period="2d")

                # 4. Fetch Daily Data for volume + trend analysis
                daily_data = await kite_data.fetch_batch(symbols, interval="1d", period="30d")

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
                    df_daily = daily_data.get(symbol)

                    # Evaluate trade with full radar
                    action, reason, new_stop = self._evaluate_trade(
                        trade, current_price, df_15m, df_daily
                    )

                    # Update trailing stop if raised
                    if new_stop > trade.stop_loss:
                        old_stop = trade.stop_loss
                        trade.stop_loss = new_stop
                        trade.updated_at = datetime.utcnow()

                        alert_msg = (
                            f"Trail Stop Raised: ₹{old_stop:.2f} → ₹{new_stop:.2f} "
                            f"({reason})"
                        )
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
                            f"🛡️ <b>GUARDIAN v2 UPDATE</b>\n"
                            f"🟢 <b>{symbol}</b>\n"
                            f"LTP: ₹{current_price:.2f}\n"
                            f"<i>{alert_msg}</i>"
                        )

                    # Handle EXIT signals (Advisory Mode Only)
                    if action == "SELL":
                        alert_msg = f"ADVISORY SELL: {reason} @ ₹{current_price:.2f}"
                        alert = TradeAlert(
                            symbol=symbol,
                            alert_type="WARNING" if "Stop Hit" in reason else "INFO",
                            message=alert_msg,
                            price_at_alert=current_price,
                            scan_date=date.today().isoformat()
                        )
                        session.add(alert)
                        alerts_generated += 1
                        print(f" 🚨 [GUARDIAN v2] SELL for {symbol}: {reason}", flush=True)

                        await notifier_service.send_telegram_alert(
                            f"🚨 <b>GUARDIAN SELL ALERT</b>\n"
                            f"🔴 <b>{symbol}</b>\n"
                            f"LTP: ₹{current_price:.2f}\n"
                            f"Reason: {reason}\n"
                            f"Nifty: {self._nifty_regime} ({self._nifty_change_pct:+.1f}%)\n"
                            f"<i>Action Required: Review position.</i>"
                        )

                    # Handle DEAD MONEY warnings
                    if action == "DEAD_MONEY":
                        alert_msg = f"DEAD MONEY: {reason}"
                        alert = TradeAlert(
                            symbol=symbol,
                            alert_type="INFO",
                            message=alert_msg,
                            price_at_alert=current_price,
                            scan_date=date.today().isoformat()
                        )
                        session.add(alert)
                        alerts_generated += 1

                        await notifier_service.send_telegram_alert(
                            f"💤 <b>DEAD MONEY ALERT</b>\n"
                            f"⚪ <b>{symbol}</b>\n"
                            f"LTP: ₹{current_price:.2f} | PnL: {((current_price - trade.entry)/trade.entry)*100:+.1f}%\n"
                            f"<i>{reason}</i>\n"
                            f"Consider redeploying capital."
                        )

                await session.commit()
                if alerts_generated > 0:
                    logger.info(f"[GUARDIAN v2] Cycle complete. Generated {alerts_generated} alerts.")

        except Exception as e:
            logger.error(f"[GUARDIAN v2] Cycle failed: {e}")
            import traceback
            traceback.print_exc()

    # =========================================================================
    # CORE EVALUATION ENGINE
    # =========================================================================
    def _evaluate_trade(
        self,
        trade: SwingTrade,
        current_price: float,
        df_15m: pd.DataFrame,
        df_daily: pd.DataFrame = None,
    ) -> tuple[str, str, float]:
        """
        Full Radar evaluation with volume, daily trend, dead money, and Nifty regime.
        Returns: (Action, Reason, NewStopLoss)
        """
        action = "HOLD"
        reason = "Trend intact."
        new_stop = trade.stop_loss

        # Radar Scoring Init
        radar_score = 50.0
        profit_pct = ((current_price - trade.entry) / trade.entry) * 100

        # Track Max Profit Reached
        scan_data = trade.scan_data or {}
        max_profit_pct = scan_data.get("max_profit_pct", 0.0)
        if profit_pct > max_profit_pct:
            max_profit_pct = profit_pct
            scan_data["max_profit_pct"] = max_profit_pct

        # Track drawdown from peak
        drawdown_from_peak = max_profit_pct - profit_pct
        scan_data["drawdown_from_peak"] = round(drawdown_from_peak, 2)
        scan_data["nifty_regime"] = self._nifty_regime
        scan_data["nifty_change"] = round(self._nifty_change_pct, 2)
        trade.scan_data = scan_data

        # ===== 1. Hard Stop Loss Hit =====
        if current_price <= trade.stop_loss:
            return "SELL", "Stop Loss Hit", new_stop

        # ===== 2. Target Hit =====
        if current_price >= trade.target:
            return "SELL", "Target Reached", new_stop

        # ===== 3. Dynamic Trailing Stop Logic (Multi-Tier) =====

        # Tier 3 (>10% gains): Trail tightly by 3%
        if max_profit_pct >= 10.0:
            tier_3_stop = round(current_price * 0.97, 2)
            if tier_3_stop > new_stop:
                new_stop = tier_3_stop
                reason = "Tier 3: Locked Gains (3% trail)"

        # Tier 2 (>5% gains): Lock in at least 2.5%
        elif max_profit_pct >= 5.0:
            tier_2_stop = round(max(trade.entry * 1.025, current_price * 0.975), 2)
            if tier_2_stop > new_stop:
                new_stop = tier_2_stop
                reason = "Tier 2: Locked >2.5%"

        # Tier 1 (>2.5% gains): Move to breakeven + 0.5%
        elif max_profit_pct >= 2.5:
            breakeven_stop = round(trade.entry * 1.005, 2)
            if breakeven_stop > new_stop:
                new_stop = breakeven_stop
                reason = "Tier 1: Capital Protected"

        # ===== 4. Nifty Regime Override =====
        # If Nifty is crashing, tighten ALL trailing stops by an extra 1%
        if self._nifty_regime == "BEARISH" and profit_pct > 1.0:
            panic_stop = round(current_price * 0.98, 2)  # 2% tight trail
            if panic_stop > new_stop:
                new_stop = panic_stop
                reason = f"Nifty Crash Override: Market {self._nifty_change_pct:+.1f}%"

        # ===== 5. Volume Analysis (Daily) =====
        vol_score, vol_desc = self._score_volume_health(df_daily)
        scan_data["volume_health"] = vol_desc
        trade.scan_data = scan_data

        # ===== 6. Dead Money Detection =====
        is_dead, dead_reason = self._check_dead_money(trade, df_daily)
        if is_dead:
            scan_data["dead_money"] = True
            scan_data["dead_money_reason"] = dead_reason
            trade.scan_data = scan_data
            # Don't override a SELL action, but flag as dead money
            if action == "HOLD":
                action = "DEAD_MONEY"
                reason = dead_reason
        else:
            scan_data["dead_money"] = False
            trade.scan_data = scan_data

        # ===== 7. Intraday Trend Analysis & Radar Scoring (15m) =====
        if df_15m is not None and not df_15m.empty and len(df_15m) > 20:
            try:
                from ta.trend import EMAIndicator
                from ta.momentum import RSIIndicator

                close_prices = df_15m['close']
                ema_20 = EMAIndicator(close=close_prices, window=20).ema_indicator().iloc[-1]
                rsi_14 = RSIIndicator(close=close_prices, window=14).rsi().iloc[-1]

                # Base score
                radar_score = 50.0 + (profit_pct * 2)

                # EMA position
                if current_price > ema_20:
                    radar_score += 12
                else:
                    radar_score -= 18

                # RSI modifiers
                if rsi_14 > 70:
                    radar_score += 8
                elif rsi_14 < 40:
                    radar_score -= 15

                # Volume modifier
                radar_score += vol_score

                # Nifty regime modifier
                if self._nifty_regime == "BEARISH":
                    radar_score -= 10
                elif self._nifty_regime == "BULLISH":
                    radar_score += 5

                # Early Exit: profitable but collapsing below EMA with weak RSI
                if profit_pct > 3.0 and current_price < ema_20 and rsi_14 < 45:
                    aggressive_stop = round(ema_20 * 0.995, 2)
                    if aggressive_stop > new_stop and current_price > aggressive_stop:
                        new_stop = aggressive_stop
                        reason = "Radar: Bearish divergence, tightening stop"
                        if action != "SELL":
                            action = "HOLD"

                trade.current_score = round(max(0, min(100, radar_score)), 1)

            except Exception as e:
                logger.debug(f"[GUARDIAN v2] 15m analysis error for {trade.symbol}: {e}")
                pass

        # ===== 8. Daily Timeframe Analysis =====
        if df_daily is not None and not df_daily.empty and len(df_daily) > 20:
            try:
                from ta.trend import EMAIndicator, ADXIndicator

                daily_close = df_daily['close']
                daily_high = df_daily['high']
                daily_low = df_daily['low']

                daily_ema_20 = EMAIndicator(close=daily_close, window=20).ema_indicator().iloc[-1]
                daily_ema_50 = EMAIndicator(close=daily_close, window=min(50, len(df_daily) - 1)).ema_indicator().iloc[-1]

                # ADX for trend strength
                adx = ADXIndicator(
                    high=daily_high, low=daily_low, close=daily_close, window=14
                ).adx().iloc[-1]

                # Daily EMA alignment
                if current_price > daily_ema_20 > daily_ema_50:
                    radar_score = (trade.current_score or 50) + 10  # Bullish alignment
                    scan_data["daily_trend"] = "BULLISH"
                elif current_price < daily_ema_20 < daily_ema_50:
                    radar_score = (trade.current_score or 50) - 15  # Bearish alignment
                    scan_data["daily_trend"] = "BEARISH"
                    # If daily structure is bearish AND profitable, tighten
                    if profit_pct > 2.0:
                        daily_ema_stop = round(daily_ema_20 * 0.99, 2)
                        if daily_ema_stop > new_stop and current_price > daily_ema_stop:
                            new_stop = daily_ema_stop
                            reason = "Daily: Bearish structure, trailing to EMA20"
                elif current_price < daily_ema_20:
                    radar_score = (trade.current_score or 50) - 8
                    scan_data["daily_trend"] = "WEAKENING"
                else:
                    scan_data["daily_trend"] = "NEUTRAL"

                # ADX trend strength
                scan_data["adx"] = round(adx, 1)
                if adx < 15:
                    radar_score -= 5  # No trend = bad for swing
                elif adx > 25:
                    radar_score += 5  # Strong trend

                trade.current_score = round(max(0, min(100, radar_score)), 1)
                trade.scan_data = scan_data

            except Exception as e:
                logger.debug(f"[GUARDIAN v2] Daily analysis error for {trade.symbol}: {e}")

        # Fallback score if no data was available
        if trade.current_score is None or trade.current_score == 0:
            trade.current_score = round(max(0, min(100, 50.0 + (profit_pct * 2))), 1)

        return action, reason, new_stop

    # =========================================================================
    # PORTFOLIO API
    # =========================================================================
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

                    scan_data = t.scan_data or {}
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
                        "last_evaluated_at": t.updated_at.isoformat() if t.updated_at else None,
                        # New v2 fields
                        "max_profit_pct": round(scan_data.get("max_profit_pct", 0), 2),
                        "drawdown_from_peak": round(scan_data.get("drawdown_from_peak", 0), 2),
                        "volume_health": scan_data.get("volume_health", "N/A"),
                        "daily_trend": scan_data.get("daily_trend", "N/A"),
                        "nifty_regime": scan_data.get("nifty_regime", "N/A"),
                        "dead_money": scan_data.get("dead_money", False),
                        "dead_money_reason": scan_data.get("dead_money_reason", ""),
                        "adx": scan_data.get("adx", 0),
                    })
        except Exception as e:
            logger.error(f"[GUARDIAN v2] Failed to get live portfolio: {e}")

        return portfolio

    async def send_portfolio_summary(self, title="HOURLY PORTFOLIO SUMMARY"):
        """Sends a full summary of all open positions to Telegram."""
        try:
            portfolio = await self.get_live_portfolio()
            if not portfolio:
                return

            msg = f"📊 <b>{title}</b>\n"
            msg += f"Nifty: {self._nifty_regime} ({self._nifty_change_pct:+.1f}%)\n"
            msg += "--------------------------\n"

            for p in portfolio:
                if p["dead_money"]:
                    icon = "💤"
                elif p["action"] == "SELL":
                    icon = "🔴"
                else:
                    icon = "🟢"

                msg += f"{icon} <b>{p['symbol']}</b> (Score: {p['current_score']})\n"
                msg += f"LTP: ₹{p['current_price']:.2f} | <b>{p['profit_pct']:+.2f}%</b>"
                if p["max_profit_pct"] > 0:
                    msg += f" (Peak: +{p['max_profit_pct']:.1f}%)"
                msg += f"\nSL: ₹{p['stop_loss']:.2f} | Vol: {p['volume_health']}\n"
                msg += f"Trend: {p['daily_trend']} | {p['action']}: {p['reason']}\n\n"

            await notifier_service.send_telegram_alert(msg)
            logger.info(f"[GUARDIAN v2] Summary sent: {title}")
        except Exception as e:
            logger.error(f"[GUARDIAN v2] Failed to send summary: {e}")

    async def run_hourly_deep_scan(self, title="HOURLY PORTFOLIO SUMMARY"):
        """Runs once an hour to deeply analyze active positions and update their AI Scores."""
        logger.info("[GUARDIAN v2] Starting hourly deep scan...")
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
                        # Preserve radar fields when updating scan_data
                        existing_scan = trade.scan_data or {}
                        radar_fields = {
                            k: existing_scan[k] for k in [
                                "max_profit_pct", "drawdown_from_peak", "volume_health",
                                "daily_trend", "nifty_regime", "nifty_change",
                                "dead_money", "dead_money_reason", "adx"
                            ] if k in existing_scan
                        }
                        trade.scan_data = {**analysis, **radar_fields}
                    else:
                        trade.current_score = 50.0
                        if trade.scan_data:
                            trade.scan_data["score"] = 50.0
                            trade.scan_data["signal"] = "HOLD"

                await session.commit()

            # Send summary
            await self.send_portfolio_summary(title=title)
        except Exception as e:
            logger.error(f"[GUARDIAN v2] Deep scan failed: {e}")

position_manager = PositionManager()

