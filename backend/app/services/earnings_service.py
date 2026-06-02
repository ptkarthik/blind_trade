import json
import os
import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "earnings_cache.json")

class EarningsService:
    """
    Offline-First Earnings Risk Manager.
    Prevents the swing engine from entering trades right before an earnings announcement,
    shielding the portfolio from binary overnight gap risk.
    """
    def __init__(self):
        self.cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    self.cache = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load earnings cache: {e}")
                self.cache = {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self.cache, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save earnings cache: {e}")

    def is_in_earnings_window(self, symbol: str) -> bool:
        """
        Check if an earnings announcement falls within the danger window [-3 days, +1 day].
        Microsecond execution via local dict lookup. Never hangs.
        Defaults to False (Fail Open) if data is missing.
        """
        if symbol not in self.cache:
            return False

        try:
            earnings_ts = self.cache[symbol].get("timestamp")
            if not earnings_ts:
                return False

            earnings_date = datetime.utcfromtimestamp(earnings_ts)
            now = datetime.utcnow()

            # Danger window: 3 days before, 1 day after
            # This protects against buying before the binary event, 
            # and prevents buying immediately on the first manic/panic day after.
            delta = earnings_date - now

            if -timedelta(days=1) <= delta <= timedelta(days=3):
                return True
                
        except Exception as e:
            logger.error(f"Earnings format error for {symbol}: {e}")
            
        return False

    def get_days_since_earnings(self, symbol: str) -> int:
        """
        Returns the number of days since the most recent earnings announcement.
        If the announcement is in the future, or data is missing, returns -1.
        """
        if symbol not in self.cache:
            return -1

        try:
            earnings_ts = self.cache[symbol].get("timestamp")
            if not earnings_ts:
                return -1

            earnings_date = datetime.utcfromtimestamp(earnings_ts)
            now = datetime.utcnow()

            delta = now - earnings_date

            if delta.days >= 0:
                return delta.days
                
        except Exception as e:
            logger.error(f"Earnings format error for {symbol}: {e}")
            
        return -1

    async def update_cache(self, symbols: list):
        """
        Background maintenance task. 
        Fetches earnings softly over time. Must never be run synchronously within scan loop.
        """
        logger.info(f" Starting Earnings Calendar sync for {len(symbols)} symbols...")
        import yfinance as yf
        updated_count = 0
        
        async def fetch_single_symbol(sym):
            def _fetch():
                try:
                    # Request only the basic info dictionary
                    t = yf.Ticker(sym)
                    info = t.info
                    if not info: return None
                    return info.get('earningsTimestamp')
                except Exception:
                    return None
                    
            try:
                # Extreme strict timeout. If yfinance hangs, we drop the symbol and move on.
                ts = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=4.0)
                if ts:
                    self.cache[sym] = {
                        "timestamp": ts,
                        "date_str": datetime.fromtimestamp(ts).strftime("%Y-%m-%d"),
                        "last_updated": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    return True
            except asyncio.TimeoutError:
                logger.debug(f" Earnings fetch timeout for {sym}")
            except Exception as e:
                logger.debug(f"️ Earnings fetch error for {sym}: {e}")
            return False

        # Concurrency of 5 to not overwhelm IP
        limit = asyncio.Semaphore(5)
        
        async def sem_task(sym):
            async with limit:
                success = await fetch_single_symbol(sym)
                # Polite humanize delay to avoid API block
                await asyncio.sleep(0.5)
                return success

        tasks = [sem_task(sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for r in results:
            if r is True: updated_count += 1

        self._save_cache()
        logger.info(f" Earnings Calendar Sync Complete. {updated_count} symbols updated.")
        return updated_count

earnings_service = EarningsService()
