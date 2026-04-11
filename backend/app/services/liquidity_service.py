
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
        self.bootstrapping_symbols = set()
        
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
        """Returns cached liquidity or a placeholder."""
        return self.liquidity_data.get(symbol, {"adv20": 0, "level": "Unknown", "last_updated": 0})

    async def get_liquidity_async(self, symbol: str) -> dict:
        """Async version that triggers a fetch if missing."""
        if symbol not in self.liquidity_data:
            await self.refresh_symbol_benchmark(symbol)
        return self.get_liquidity(symbol)

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

    async def bulk_bootstrap(self, symbols: list[str]):
        """Bootstraps ADV20 for a large batch of symbols in one go."""
        if not symbols: return
        
        # Track what we are bootstrapping to avoid redundant probes
        new_symbols = [s for s in symbols if s not in self.bootstrapping_symbols]
        if not new_symbols: return
        
        self.bootstrapping_symbols.update(new_symbols)
        if len(new_symbols) > 5:
            print(f"🛰️ [LIQ BOOTSTRAP] Starting bulk load for {len(new_symbols)} symbols...")
        
        try:
            results = await market_service.get_batch_ohlc(new_symbols, interval="1d", period="1mo")
            
            count = 0
            for symbol, df in results.items():
                if not df.empty:
                    adv = df['volume'].tail(20).mean()
                    self.liquidity_data[symbol] = {
                        "adv20": round(float(adv), 0),
                        "level": self.classify_liquidity(adv),
                        "last_updated": time.time()
                    }
                    count += 1
            
            if count > 0:
                if len(new_symbols) > 5:
                    print(f"✅ [LIQ BOOTSTRAP] Successfully mapped {count} symbols.")
                self._save_cache()
            
            # Clean up tracking set
            for s in new_symbols: self.bootstrapping_symbols.discard(s)
            
        except Exception as e:
            print(f"❌ [LIQ BOOTSTRAP] Bulk load failed: {e}")
            for s in new_symbols: self.bootstrapping_symbols.discard(s)

    async def refresh_symbol_benchmark(self, symbol: str):
        """Calculates ADV20 with Hardened Multi-Tier Failover."""
        # 1. TIER 1: Cache Check (Highest Efficiency)
        if symbol in self.liquidity_data:
            # Refresh only if older than 24 hours
            if time.time() - self.liquidity_data[symbol].get("last_updated", 0) < 86400:
                return

        # 2. TIER 2: Fast Browser-Mimicry Probe via YahooFast
        from app.services.yahoo_fast import yahoo_fast
        
        try:
            df = await yahoo_fast.fetch_ohlc(symbol, period="1mo", interval="1d")
            if not df.empty:
                adv = df['volume'].tail(20).mean()
                if adv > 0:
                    self.liquidity_data[symbol] = {
                        "adv20": round(float(adv), 0),
                        "level": self.classify_liquidity(adv),
                        "last_updated": time.time()
                    }
                    self._save_cache()
                    return
        except Exception as e:
            print(f"Liquidity Single Probe Failed for {symbol}: {e}")
            pass

        # 3. TIER 3: Bulk Request (Fallback)
        # If single fails, we queue it for the next bulk run or do a small batch
        await self.bulk_bootstrap([symbol])

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
