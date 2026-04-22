import asyncio
import pandas as pd
import json
import random
from datetime import datetime
from curl_cffi import requests
from typing import Dict, List, Any

class YahooFast:
    """[V12.4] Hyper-Speed Browser-Mimicry Data Provider."""
    
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
        ]
        self.session = None

    async def _get_session(self):
        if self.session is None:
            # We use AsyncSession for persistent keep-alive connections
            self.session = requests.AsyncSession(
                impersonate="chrome120",
                headers={
                    "Accept": "*/*",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Origin": "https://finance.yahoo.com",
                    "Referer": "https://finance.yahoo.com/",
                }
            )
        return self.session

    async def fetch_ohlc(self, symbol: str, period: str = "7d", interval: str = "15m") -> pd.DataFrame:
        """Fetches OHLC data directly from Yahoo Chart API with Browser Mimicry."""
        # Convert period/interval to Yahoo format if needed
        # Yahoo Chart API uses 'range' and 'interval'
        params = {
            "range": period,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits,capitalGains"
        }
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        session = await self._get_session()
        
        try:
            # Mimic a real browser request
            resp = await session.get(url, params=params, timeout=10)
            if resp.status_code != 200:
                return pd.DataFrame()
            
            data = resp.json()
            chart = data.get("chart", {}).get("result", [None])[0]
            if not chart:
                return pd.DataFrame()
            
            # Parse the sparse JSON response into OHLC DataFrame
            timestamp = chart.get("timestamp", [])
            indicators = chart.get("indicators", {}).get("quote", [{}])[0]
            
            if not timestamp or not indicators:
                return pd.DataFrame()
                
            df = pd.DataFrame({
                "open": indicators.get("open", []),
                "high": indicators.get("high", []),
                "low": indicators.get("low", []),
                "close": indicators.get("close", []),
                "volume": indicators.get("volume", [])
            }, index=pd.to_datetime(timestamp, unit="s"))
            
            # Drop any NaN rows and handle column naming
            df = df.dropna()
            return df
            
        except Exception as e:
            print(f"❌ YahooFast Error [{symbol}]: {str(e)}")
            return pd.DataFrame()

    async def fetch_batch(self, symbols: List[str], interval: str = "15m", period: str = "7d", concurrency: int = 25) -> Dict[str, pd.DataFrame]:
        """Fetches a batch of symbols at high speed using parallel ribbons."""
        results = {}
        semaphore = asyncio.Semaphore(concurrency)
        
        async def _worker(sym):
            async with semaphore:
                # Add tiny random jitter to avoid perfect robotic synchronization
                await asyncio.sleep(random.uniform(0.1, 0.4))
                df = await self.fetch_ohlc(sym, period=period, interval=interval)
                # [V23 FIX #16] Single retry for individual symbol failures
                # OLD: Failed symbols silently returned empty DF with no retry, losing ~5% per scan
                if df.empty:
                    await asyncio.sleep(random.uniform(0.5, 1.0))
                    df = await self.fetch_ohlc(sym, period=period, interval=interval)
                if not df.empty:
                    results[sym] = df
        
        await asyncio.gather(*[_worker(s) for s in symbols])
        return results

yahoo_fast = YahooFast()
