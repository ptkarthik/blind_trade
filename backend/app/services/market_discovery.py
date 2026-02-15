import pandas as pd
import requests
import os
import io
import time
from typing import List, Dict

class MarketDiscoveryService:
    def __init__(self):
        self.NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.cache_file = os.path.join(self.cache_dir, "nse_market_list.json")
        self.CACHE_DURATION = 86400 # 24 hours
        
    def _fetch_nse_list(self) -> List[Dict]:
        """Fetches the official CSV from NSE and parses symbols."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
        }
        try:
            response = requests.get("https://archives.nseindia.com/content/equities/EQUITY_L.csv", headers=headers, timeout=15)
            response.raise_for_status()
            
            df = pd.read_csv(io.StringIO(response.text))
            stocks = []
            for _, row in df.iterrows():
                symbol = str(row['SYMBOL']).strip()
                name = str(row['NAME OF COMPANY']).strip()
                series = str(row[' SERIES']).strip() # Note the leading space in some NSE CSVs
                
                # Only include main equity series (EQ or BE)
                if series in ['EQ', 'BE']:
                    stocks.append({
                        "symbol": f"{symbol}.NS",
                        "name": name,
                        "raw_symbol": symbol
                    })
            return stocks
        except Exception as e:
            print(f"MarketDiscovery: Fetch failed: {e}")
            return []

    async def get_full_market_list(self) -> List[Dict]:
        """Returns the full list of NSE stocks, using cache if valid."""
        import json
        
        # 1. Check Cache
        if os.path.exists(self.cache_file):
            mtime = os.path.getmtime(self.cache_file)
            if (time.time() - mtime) < self.CACHE_DURATION:
                try:
                    with open(self.cache_file, "r") as f:
                        return json.load(f)
                except: pass
        
        # 2. Fetch Fresh
        print("📡 MarketDiscovery: Fetching fresh NSE equity list...")
        import asyncio
        stocks = await asyncio.to_thread(self._fetch_nse_list)
        
        if stocks:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(self.cache_file, "w") as f:
                    json.dump(stocks, f, indent=4)
            except Exception as e:
                print(f"MarketDiscovery: Cache save failed: {e}")
            return stocks
            
        return []

market_discovery = MarketDiscoveryService()
