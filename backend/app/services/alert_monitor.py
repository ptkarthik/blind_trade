import logging
import asyncio
from datetime import datetime
from app.services.kite_data import kite_data
from app.services.notification_service import notification_service
from app.services.trade_manager import trade_manager

logger = logging.getLogger(__name__)

class AlertMonitor:
    """
    Monitors market conditions (Nifty, active trades) and triggers notifications.
    Intended to run every 30 minutes.
    """
    def __init__(self):
        self.last_nifty_price = None

    async def run_periodic_summary(self):
        """Runs the 30-minute summary check."""
        logger.info(" Running half-hourly market summary...")
        
        if not kite_data.is_ready:
            logger.warning("️ AlertMonitor: Kite data not ready, skipping summary.")
            return

        try:
            # 1. Check Nifty 50
            ltp_data = await kite_data.get_ltp(["NIFTY 50"])
            nifty_data = ltp_data.get("NIFTY 50")
            
            nifty_summary = ""
            if nifty_data:
                price = nifty_data.get("price", 0)
                change_pct = nifty_data.get("change_percent", 0)
                
                status_icon = "" if change_pct >= 0 else ""
                nifty_summary = f"{status_icon} <b>NIFTY 50</b>: {price} ({change_pct}%)\n"
                
                # Check for significant movement or zero crossing
                if self.last_nifty_price is not None:
                    last_pct = self.last_nifty_price.get("change_percent", 0)
                    if (last_pct < 0 and change_pct >= 0) or (last_pct >= 0 and change_pct < 0):
                        nifty_summary = f" <b>TREND CHANGE</b> \n" + nifty_summary
                    elif abs(change_pct - last_pct) >= 1.0:
                        nifty_summary = f" <b>1% MOVEMENT</b> \n" + nifty_summary
                
                self.last_nifty_price = nifty_data

            # 2. Get Active Trades Summary
            active_trades = trade_manager.get_active_trades()
            trades_summary = ""
            if active_trades:
                trades_summary = "\n <b>Active Positions:</b>\n"
                symbols = [t["symbol"] for t in active_trades]
                live_prices = await kite_data.get_ltp(symbols)
                
                for t in active_trades:
                    sym = t["symbol"]
                    entry = t["entry"]
                    live_info = live_prices.get(sym, {})
                    live_price = live_info.get("price", entry)
                    
                    if entry > 0:
                        pnl_pct = ((live_price - entry) / entry) * 100
                    else:
                        pnl_pct = 0
                        
                    t_icon = "" if pnl_pct >= 0 else ""
                    trades_summary += f"{t_icon} {sym}: {live_price} ({pnl_pct:.2f}%)\n"
            else:
                trades_summary = "\n No active positions."

            # Construct and send final message
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            final_message = f" <b>Market Summary ({timestamp})</b>\n\n{nifty_summary}{trades_summary}"
            
            notification_service.send_mobile_alert(final_message)
            
        except Exception as e:
            logger.error(f" AlertMonitor Error: {e}")

alert_monitor = AlertMonitor()
