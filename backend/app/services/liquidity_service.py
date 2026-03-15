
import pandas as pd
import numpy as np
import os
import json
import time
import asyncio
from datetime import datetime
import yfinance as yf
from app.services.market_data import market_service
from app.services.market_discovery import market_discovery
from app.core.config import settings

class LiquidityService:
    def __init__(self):
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.liquidity_cache_file = os.path.join(self.cache_dir, "liquidity_master.json")
        self.benchmarks_cache_file = os.path.join(self.cache_dir, "volume_benchmarks.json")
        self.CACHE_DURATION = 86400 # 24 hours
        
        self.liquidity_data = {} # Symbol -> {adv20, level, last_updated}
        self.benchmarks = {} # Symbol -> {time_bucket (e.g. "09:30"): avg_vol}
        
    def _get_time_bucket(self, dt):
        """Standardizes datetime to HH:MM bucket."""
        return dt.strftime("%H:%M")

    async def initialize(self):
        """Loads cache or triggers refresh."""
        if os.path.exists(self.liquidity_cache_file):
            try:
                mtime = os.path.getmtime(self.liquidity_cache_file)
                if (time.time() - mtime) < self.CACHE_DURATION:
                    with open(self.liquidity_cache_file, "r") as f:
                        self.liquidity_data = json.load(f)
                    if os.path.exists(self.benchmarks_cache_file):
                        with open(self.benchmarks_cache_file, "r") as f:
                            self.benchmarks = json.load(f)
                    print(f"✅ LiquidityService: Loaded cache for {len(self.liquidity_data)} symbols.")
                    return
            except Exception as e:
                print(f"LiquidityService: Cache load error: {e}")
        
        # If no cache or stale, we'll wait for first scan or trigger a background refresh
        # (Implementing background refresh below)

    def get_liquidity(self, symbol: str) -> dict:
        return self.liquidity_data.get(symbol, {"adv20": 0, "level": "Unknown", "last_updated": 0})

    def get_benchmark_vol(self, symbol: str, time_bucket: str) -> float:
        return self.benchmarks.get(symbol, {}).get(time_bucket, 0)

    def classify_liquidity(self, adv):
        if adv < 200000: return "Very Low"
        if adv < 500000: return "Low"
        if adv < 2000000: return "Moderate"
        return "High"

    async def refresh_all_benchmarks(self, symbols: list):
        """
        Intensive background task to fetch 20-day historical data and calculate benchmarks.
        """
        print(f"🔄 LiquidityService: Refreshing benchmarks for {len(symbols)} symbols...")
        
        # To avoid blocking, we could process in batches
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i+batch_size]
            tasks = [self.refresh_symbol_benchmark(s) for s in batch]
            await asyncio.gather(*tasks)
            
            # Save progress periodically
            self._save_cache()
            await asyncio.sleep(1) # Breath
            
        print("✅ LiquidityService: All benchmarks refreshed.")

    async def refresh_symbol_benchmark(self, symbol: str):
        """Calculates ADV20 and Same-Time average volume for one symbol."""
        try:
            # Fetch 1 month of 15m data (covers 20 trading days)
            df = await market_service.get_historical_intraday(symbol, interval="15m", period="1mo")
            if df.empty: return
            
            # 1. Calculate ADV20
            daily_vols = df['volume'].resample('1D').sum()
            daily_vols = daily_vols[daily_vols > 0].tail(20)
            adv20 = daily_vols.mean()
            
            self.liquidity_data[symbol] = {
                "adv20": round(float(adv20), 0),
                "level": self.classify_liquidity(adv20),
                "last_updated": time.time()
            }
            
            # 2. Calculate Time Buckets Benchmarks
            # Group by time of day
            df['time_bucket'] = df.index.map(self._get_time_bucket)
            # Filter for last 20 days
            last_20_days = df.index.unique().date[-20:]
            df_20 = df[df.index.date.isin(last_20_days)]
            
            time_avg = df_20.groupby('time_bucket')['volume'].mean()
            self.benchmarks[symbol] = time_avg.to_dict()
            
        except Exception as e:
            # print(f"LiquidityService: Refresh failed for {symbol}: {e}")
            pass

    def _save_cache(self):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self.liquidity_cache_file, "w") as f:
                json.dump(self.liquidity_data, f)
            with open(self.benchmarks_cache_file, "w") as f:
                json.dump(self.benchmarks, f)
        except Exception as e:
            print(f"LiquidityService: Cache save error: {e}")

liquidity_service = LiquidityService()
