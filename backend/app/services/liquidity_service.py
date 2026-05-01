
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
        return self.liquidity_data.get(symbol, {"adv20": 0, "turnover_3d": 0, "level": "Unknown", "last_updated": 0})

    async def get_liquidity_async(self, symbol: str) -> dict:
        """Async version that triggers a fetch if missing."""
        if symbol not in self.liquidity_data:
            await self.refresh_symbol_benchmark(symbol)
        return self.get_liquidity(symbol)

    def get_benchmark_vol(self, symbol: str, time_bucket: str) -> float:
        return self.benchmarks.get(symbol, {}).get(time_bucket, 0)

    def build_time_benchmarks_from_15m(self, batch_15m_data: dict):
        """[V31 GAP#1 FIX] Build per-time-bucket volume benchmarks from 15m batch data.
        
        This is called during intraday scan with the already-fetched 15m OHLCV.
        Groups volume by HH:MM time bucket to give accurate time-of-day baselines.
        Without this, RVOL fallback divides ADV20/candles_per_session which doesn't
        account for opening surge (9:15-9:30 vol is 3-5x midday volume).
        """
        if not batch_15m_data:
            return
        
        built_count = 0
        for symbol, df in batch_15m_data.items():
            if df is None or not hasattr(df, 'index') or df.empty:
                continue
            # Skip if already has benchmarks (avoid overwriting with partial data)
            if symbol in self.benchmarks and len(self.benchmarks[symbol]) >= 10:
                continue
            try:
                if not isinstance(df.index, pd.DatetimeIndex):
                    continue
                
                # Convert to IST for correct time bucketing
                idx = df.index
                if idx.tz is None:
                    ist_times = idx + pd.Timedelta(hours=5, minutes=30)
                else:
                    try:
                        ist_times = idx.tz_convert('Asia/Kolkata')
                    except Exception:
                        ist_times = idx
                
                time_buckets = ist_times.strftime('%H:%M')
                vol_series = df['volume']
                if isinstance(vol_series, pd.DataFrame):
                    vol_series = vol_series.iloc[:, 0]
                
                # Group by time bucket and take median
                bucket_df = pd.DataFrame({'bucket': time_buckets, 'volume': vol_series.values})
                benchmarks = bucket_df.groupby('bucket')['volume'].median().to_dict()
                
                if benchmarks:
                    self.benchmarks[symbol] = {k: round(float(v), 0) for k, v in benchmarks.items()}
                    built_count += 1
            except Exception:
                continue
        
        if built_count > 0:
            self._save_cache()

    def classify_liquidity(self, adv, price=0.0, turnover_3d=0.0):
        # FIX #4/V17: Multi-Day Persistence Liquidity (Turnover in Crores)
        # Turnover Persistence: We use the minimum of (ADV20 x Price) and 3-day avg Turnover
        # This prevents "one-day volume flukes" from qualifying illiquid stocks.
        
        turnover_base = (adv * price)
        # If turnover_3d is provided, use it to verify persistence
        effective_turnover = min(turnover_base, turnover_3d) if turnover_3d > 0 else turnover_base
        
        turnover_cr = effective_turnover / 1e7  # Convert to Crores
        if turnover_cr < 1 or price == 0:   return "Very Low"   # < ₹1 Cr
        if turnover_cr < 10:                 return "Low"        # ₹1-10 Cr
        if turnover_cr < 50:                 return "Moderate"   # ₹10-50 Cr
        return "High"                                            # > ₹50 Cr

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
                    # V17: Calculate 3-day persistence turnover
                    # turnover = volume * close
                    df['turnover'] = df['volume'] * df['close']
                    turnover_3d = df['turnover'].tail(3).mean()
                    
                    last_price = float(df['close'].iloc[-1]) if 'close' in df.columns and not df.empty else 0.0
                    self.liquidity_data[symbol] = {
                        "adv20": round(float(adv), 0),
                        "turnover_3d": round(float(turnover_3d), 0),
                        "level": self.classify_liquidity(adv, last_price, turnover_3d=turnover_3d),
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
                    df['turnover'] = df['volume'] * df['close']
                    turnover_3d = df['turnover'].tail(3).mean()
                    last_price = float(df['close'].iloc[-1]) if 'close' in df.columns else 0.0
                    self.liquidity_data[symbol] = {
                        "adv20": round(float(adv), 0),
                        "turnover_3d": round(float(turnover_3d), 0),
                        "level": self.classify_liquidity(adv, last_price, turnover_3d=turnover_3d),
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
