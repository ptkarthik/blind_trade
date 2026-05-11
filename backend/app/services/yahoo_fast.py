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
        """Fetches OHLC data directly from Yahoo Chart API with Browser Mimicry (No Proxies)."""
        params = {
            "range": period,
            "interval": interval,
            "includePrePost": "false",
            "events": "div,splits,capitalGains"
        }
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        session = await self._get_session()
        
        req_kwargs = {"params": params, "timeout": 15}
        
        try:
            # Mimic a real browser request
            resp = await session.get(url, **req_kwargs)
            if resp.status_code != 200:
                # Fallback to standard requests if curl_cffi is blocked
                import requests as std_requests
                resp = await asyncio.to_thread(std_requests.get, url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
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
            # ConnectionError usually means TCP reset from too many parallel hits
            if "curl: (55)" in str(e) or "curl: (56)" in str(e):
                try:
                    import requests as std_requests
                    resp = await asyncio.to_thread(std_requests.get, url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        chart = data.get("chart", {}).get("result", [None])[0]
                        if chart:
                            timestamp = chart.get("timestamp", [])
                            indicators = chart.get("indicators", {}).get("quote", [{}])[0]
                            if timestamp and indicators:
                                df = pd.DataFrame({
                                    "open": indicators.get("open", []),
                                    "high": indicators.get("high", []),
                                    "low": indicators.get("low", []),
                                    "close": indicators.get("close", []),
                                    "volume": indicators.get("volume", [])
                                }, index=pd.to_datetime(timestamp, unit="s"))
                                return df.dropna()
                except: pass
                
            print(f"YahooFast Error [{symbol}]: {repr(e)}") # reduced noise
            return pd.DataFrame()

    async def fetch_batch(self, symbols: List[str], interval: str = "15m", period: str = "7d", concurrency: int = 5) -> Dict[str, pd.DataFrame]:
        """Fetches a batch of symbols at high speed using parallel ribbons with robust retry."""
        results = {}
        semaphore = asyncio.Semaphore(concurrency)
        
        async def _worker(sym):
            async with semaphore:
                # Add tiny random jitter to avoid perfect robotic synchronization
                await asyncio.sleep(random.uniform(0.5, 2.0))
                
                # 3-Attempt Exponential Backoff Retry (No Proxy)
                for attempt in range(3):
                    df = await self.fetch_ohlc(sym, period=period, interval=interval)
                    if not df.empty:
                        results[sym] = df
                        break
                    else:
                        # If empty, wait and retry (longer wait per attempt)
                        await asyncio.sleep(random.uniform(0.5, 1.5) * (attempt + 1))
        
        await asyncio.gather(*[_worker(s) for s in symbols])
        return results

yahoo_fast = YahooFast()
