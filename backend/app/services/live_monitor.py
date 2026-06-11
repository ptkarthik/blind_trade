"""
[LIVE MONITOR] Intraday Tracker & Alert Engine
==============================================
Runs in the background every 15 minutes during market hours.
Monitors the Top 10 tracked stocks, compares their live price against
targets and stop losses, and generates persistent alerts.
"""

import logging
from datetime import datetime, date
from typing import Dict, Any, List

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.scan_snapshot import ScanSnapshot
from app.models.trade_alert import TradeAlert

logger = logging.getLogger("live_monitor")


class LiveMonitorService:
    async def run_intraday_check(self):
        """
        Main scheduled job.
        Fetches today's active recommendations, gets live prices,
        and generates alerts if limits are breached.
        """
        today = date.today().isoformat()
        print(f" [LIVE MONITOR] Running intraday check for {today}...")

        try:
            async with AsyncSessionLocal() as session:
                # Fetch today's snapshots that haven't been locked in EOD
                stmt = select(ScanSnapshot).where(
                    ScanSnapshot.scan_date == today,
                    ScanSnapshot.is_tracked == False
                )
                result = await session.execute(stmt)
                snapshots = result.scalars().all()

                if not snapshots:
                    print(" [LIVE MONITOR] No active stocks to monitor today.")
                    return

                # Get unique symbols
                symbols = [snap.symbol for snap in snapshots]

                # Fetch live prices
                prices = await self._fetch_live_prices(symbols)
                if not prices:
                    print(" [LIVE MONITOR] Failed to fetch live prices.")
                    return

                alerts_generated = 0

                for snap in snapshots:
                    price_data = prices.get(snap.symbol)
                    if not price_data:
                        continue

                    current_price = price_data.get("price", 0)
                    if current_price <= 0:
                        continue

                    # Determine live status
                    status, alert_type, message = self._evaluate_status(snap, current_price)

                    if alert_type:
                        # Check if we already generated this exact alert today to prevent spam
                        alert_exists = await self._check_alert_exists(session, snap.symbol, today, alert_type)
                        
                        if not alert_exists:
                            alert = TradeAlert(
                                symbol=snap.symbol,
                                alert_type=alert_type,
                                message=message,
                                price_at_alert=current_price,
                                scan_date=today
                            )
                            session.add(alert)
                            alerts_generated += 1
                            print(f" [ALERT] {snap.symbol}: {message}")

                if alerts_generated > 0:
                    await session.commit()
                    print(f" [LIVE MONITOR] Check complete. {alerts_generated} new alerts generated.")

        except Exception as e:
            logger.error(f"[LIVE MONITOR] Execution failed: {e}")
            import traceback
            traceback.print_exc()

    def _evaluate_status(self, snap: ScanSnapshot, current_price: float) -> tuple[str, str | None, str | None]:
        """
        Compares live price to SL/Target.
        Returns (StatusText, AlertTypeToGenerate, AlertMessage)
        """
        entry = snap.entry_price or 0
        sl = snap.stop_loss or 0
        target = snap.target or 0

        # If we don't have proper SL/Target, just return HOLD
        if entry == 0 or sl == 0:
            return ("HOLD", None, None)

        change_pct = ((current_price - entry) / entry) * 100

        # 1. Stop Loss Hit
        if current_price <= sl:
            return ("SELL NOW (SL Hit)", "STOP_LOSS", f"Stop Loss hit at ₹{current_price} ({round(change_pct, 1)}%). Exit immediately.")

        # 2. Target Hit
        if target > 0 and current_price >= target:
            return ("TAKE PROFIT (Target Hit)", "TARGET", f"Target hit at ₹{current_price} (+{round(change_pct, 1)}%). Consider booking profit.")

        # 3. Near Stop Loss (Warning)
        sl_distance = ((current_price - sl) / sl) * 100
        if 0 < sl_distance <= 1.0:
            return ("WARNING (Near SL)", "WARNING", f"Price ₹{current_price} is within 1% of Stop Loss (₹{sl}).")

        # 4. Trailing Profit (Good)
        if change_pct > 2.0:
            return ("HOLD (In Profit)", None, None)

        return ("HOLD (Safe)", None, None)

    async def _check_alert_exists(self, session, symbol: str, scan_date: str, alert_type: str) -> bool:
        """Prevents duplicate alerts for the same stock on the same day."""
        stmt = select(TradeAlert).where(
            TradeAlert.symbol == symbol,
            TradeAlert.scan_date == scan_date,
            TradeAlert.alert_type == alert_type
        )
        result = await session.execute(stmt)
        return result.scalars().first() is not None

    async def _fetch_live_prices(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches current prices using Kite (primary) or market_data (fallback)."""
        try:
            from app.services.kite_data import kite_data
            if kite_data.is_ready:
                prices = await kite_data.get_ltp(symbols)
                if prices:
                    return prices
        except Exception as e:
            logger.debug(f"Kite LTP failed, falling back: {e}")

        # Fallback
        try:
            from app.services.market_data import market_service
            prices = await market_service.get_batch_prices(symbols)
            return prices or {}
        except Exception as e:
            logger.error(f"All price fetching failed: {e}")
            return {}

    async def get_live_dashboard(self, scan_date: str = None) -> Dict[str, Any]:
        """
        API endpoint helper: Fetches today's active stocks, their live prices,
        and dynamically calculates their hold/sell status.
        """
        if scan_date is None:
            scan_date = date.today().isoformat()

        try:
            async with AsyncSessionLocal() as session:
                # 1. Get Stocks
                stmt = select(ScanSnapshot).where(ScanSnapshot.scan_date == scan_date).order_by(ScanSnapshot.rank)
                result = await session.execute(stmt)
                snapshots = result.scalars().all()

                if not snapshots:
                    return {"status": "NO_DATA", "stocks": []}

                symbols = [snap.symbol for snap in snapshots]
                prices = await self._fetch_live_prices(symbols)

                # 2. Get Alerts
                stmt_alerts = select(TradeAlert).where(TradeAlert.scan_date == scan_date).order_by(TradeAlert.created_at.desc())
                res_alerts = await session.execute(stmt_alerts)
                alerts = res_alerts.scalars().all()

                alerts_data = [{
                    "id": a.id,
                    "symbol": a.symbol,
                    "type": a.alert_type,
                    "message": a.message,
                    "price": a.price_at_alert,
                    "time": a.created_at.isoformat(),
                    "is_read": a.is_read
                } for a in alerts]

                # 3. Build Live Dashboard
                stocks_data = []
                for snap in snapshots:
                    current_price = snap.eod_price if snap.is_tracked else (prices.get(snap.symbol, {}).get("price", snap.entry_price))
                    
                    if snap.is_tracked:
                        # Market is closed, evaluation is done
                        status = snap.performance_tag
                    else:
                        # Market is live
                        status, _, _ = self._evaluate_status(snap, current_price)

                    change_pct = ((current_price - snap.entry_price) / max(snap.entry_price, 1)) * 100

                    stocks_data.append({
                        "rank": snap.rank,
                        "symbol": snap.symbol,
                        "name": snap.name,
                        "strategy": snap.strategy,
                        "entry_price": snap.entry_price,
                        "stop_loss": snap.stop_loss,
                        "target": snap.target,
                        "current_price": current_price,
                        "change_pct": round(change_pct, 2),
                        "live_status": status,
                        "is_tracked": snap.is_tracked
                    })

                return {
                    "status": "OK",
                    "date": scan_date,
                    "stocks": stocks_data,
                    "alerts": alerts_data
                }
        except Exception as e:
            return {"status": "ERROR", "error": str(e)}


live_monitor = LiveMonitorService()
