"""
NSE Delivery Data Service [V45.2]
==================================
Fetches security-wise delivery position data from NSE Bhavcopy.
Delivery % is the single best signal of institutional conviction:
  - Delivery > 60%: Institutions are TAKING DELIVERY (holding, not day-trading)
  - Delivery < 30%: Mostly intraday speculation (noise volume)

NSE publishes this daily at:
  https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{DDMMYYYY}.csv
"""

import os
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional
import pandas as pd

logger = logging.getLogger(__name__)

# Cache directory for downloaded bhavcopy files
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "delivery_cache")


class DeliveryService:
    """
    Fetches and caches NSE delivery percentage data.
    Primary source: NSE Bhavcopy (security-wise delivery position).
    """

    def __init__(self):
        self._cache: Dict[str, Dict[str, float]] = {}  # date_str -> {symbol: delivery_pct}
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": "https://www.nseindia.com/",
        }
        os.makedirs(CACHE_DIR, exist_ok=True)

    async def get_delivery_pct(self, symbol: str, date: datetime = None) -> Optional[float]:
        """
        Returns the delivery % for a symbol on a given date.
        Returns None if data is unavailable.
        
        Args:
            symbol: NSE symbol with .NS suffix (e.g., "INFOBEAN.NS")
            date: Date to fetch (defaults to previous trading day)
        """
        if date is None:
            date = self._get_last_trading_day()

        date_str = date.strftime("%Y-%m-%d")
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()

        # Check memory cache
        if date_str in self._cache:
            return self._cache[date_str].get(clean_sym)

        # Check file cache
        cache_file = os.path.join(CACHE_DIR, f"delivery_{date.strftime('%Y%m%d')}.csv")
        if os.path.exists(cache_file):
            try:
                df = pd.read_csv(cache_file)
                self._load_cache_from_df(df, date_str)
                return self._cache.get(date_str, {}).get(clean_sym)
            except Exception:
                pass

        # Download from NSE
        try:
            df = await self._download_bhavcopy(date)
            if df is not None and not df.empty:
                df.to_csv(cache_file, index=False)
                self._load_cache_from_df(df, date_str)
                return self._cache.get(date_str, {}).get(clean_sym)
        except Exception as e:
            logger.debug(f"Delivery data unavailable for {date_str}: {e}")

        return None

    async def get_batch_delivery(self, symbols: list, date: datetime = None) -> Dict[str, float]:
        """
        Returns delivery % for multiple symbols at once.
        More efficient than calling get_delivery_pct per symbol.
        """
        if date is None:
            date = self._get_last_trading_day()

        date_str = date.strftime("%Y-%m-%d")

        # Ensure data is loaded
        if date_str not in self._cache:
            await self.get_delivery_pct(symbols[0] if symbols else "RELIANCE.NS", date)

        results = {}
        for sym in symbols:
            clean = sym.replace(".NS", "").replace(".BO", "").upper()
            val = self._cache.get(date_str, {}).get(clean)
            if val is not None:
                results[sym] = val
        return results

    async def get_avg_delivery(self, symbol: str, days: int = 5) -> Optional[float]:
        """
        Returns average delivery % over the last N trading days.
        More robust than single-day reading — institutional accumulation persists.
        """
        clean_sym = symbol.replace(".NS", "").replace(".BO", "").upper()
        values = []
        
        date = datetime.now()
        attempts = 0
        
        while len(values) < days and attempts < days + 10:
            date -= timedelta(days=1)
            attempts += 1
            
            if date.weekday() >= 5:  # Skip weekends
                continue
            
            pct = await self.get_delivery_pct(symbol, date)
            if pct is not None:
                values.append(pct)
        
        return round(sum(values) / len(values), 2) if values else None

    def _load_cache_from_df(self, df: pd.DataFrame, date_str: str):
        """Parse bhavcopy DataFrame into memory cache."""
        cache = {}
        
        # NSE Bhavcopy columns vary slightly, handle common formats
        symbol_col = None
        delivery_col = None
        traded_col = None
        
        for col in df.columns:
            col_lower = col.strip().lower()
            if col_lower in ['symbol', ' symbol']:
                symbol_col = col
            elif 'deliv' in col_lower and '%' in col_lower:
                delivery_col = col  # Direct % column
            elif 'deliv' in col_lower and 'qty' in col_lower:
                delivery_col = col  # Delivery quantity
            elif 'trd' in col_lower and 'qty' in col_lower and 'total' in col_lower.replace(' ', ''):
                traded_col = col  # Total traded quantity
            elif col_lower.strip() == 'ttl_trd_qnty':
                traded_col = col
            elif col_lower.strip() == 'dly_qt':
                delivery_col = col
            elif col_lower.strip() == 'dly_pct':
                delivery_col = col  # Direct % column
        
        if symbol_col is None:
            # Try first column as symbol
            symbol_col = df.columns[0]
        
        for _, row in df.iterrows():
            try:
                sym = str(row[symbol_col]).strip().upper()
                
                if delivery_col and '%' in str(delivery_col).lower():
                    # Direct percentage column
                    pct = float(row[delivery_col])
                elif delivery_col and traded_col:
                    # Calculate from qty
                    deliv_qty = float(row[delivery_col])
                    traded_qty = float(row[traded_col])
                    pct = (deliv_qty / traded_qty * 100) if traded_qty > 0 else 0
                elif delivery_col:
                    pct = float(row[delivery_col])
                else:
                    continue
                
                if 0 <= pct <= 100:
                    cache[sym] = round(pct, 2)
            except (ValueError, KeyError):
                continue
        
        self._cache[date_str] = cache
        logger.info(f"Loaded delivery data for {date_str}: {len(cache)} symbols")

    async def _download_bhavcopy(self, date: datetime) -> Optional[pd.DataFrame]:
        """Download NSE Bhavcopy CSV for a specific date."""
        import aiohttp
        
        # NSE Bhavcopy URL format
        date_str = date.strftime("%d%m%Y")
        urls = [
            f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{date_str}.csv",
            f"https://nsearchives.nseindia.com/content/cm/BhsecDly_{date.strftime('%d%m%Y')}.csv",
        ]
        
        for url in urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10), ssl=False) as resp:
                        if resp.status == 200:
                            content = await resp.text()
                            if ',' in content and len(content) > 100:
                                from io import StringIO
                                df = pd.read_csv(StringIO(content))
                                if len(df) > 10:
                                    return df
            except Exception as e:
                logger.debug(f"Bhavcopy download failed from {url}: {e}")
                continue
        
        # Fallback: try requests (sync, in thread)
        try:
            import requests
            def _sync_download():
                for url in urls:
                    try:
                        r = requests.get(url, headers=self._headers, timeout=10, verify=False)
                        if r.status_code == 200 and len(r.text) > 100:
                            from io import StringIO
                            return pd.read_csv(StringIO(r.text))
                    except Exception:
                        continue
                return None
            return await asyncio.to_thread(_sync_download)
        except Exception as e:
            logger.debug(f"Sync bhavcopy download also failed: {e}")
        
        return None

    def _get_last_trading_day(self) -> datetime:
        """Returns the most recent trading day (skips weekends)."""
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        
        # If before 6PM IST, use yesterday (today's data not yet published)
        if now.hour < 18:
            now -= timedelta(days=1)
        
        # Skip weekends
        while now.weekday() >= 5:
            now -= timedelta(days=1)
        
        return now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)


# Singleton
delivery_service = DeliveryService()
