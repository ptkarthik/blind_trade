import os
import json
import asyncio
import time
import pandas as pd
from typing import Dict, Any, List

class MacroCacheService:
    def __init__(self):
        self.cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "macro_cache.json")
        self.cache_data = {"1d": {}, "60m": {}, "last_updated": 0}
        self.is_syncing = False
        self._load_cache()

    def _load_cache(self):
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    data = json.load(f)
                    self.cache_data = data
                print(f" [MACRO CACHE] Loaded {len(self.cache_data.get('1d', {}))} 1d charts from disk")
        except Exception as e:
            print(f" [MACRO CACHE] Failed to load cache: {e}")

    def _save_cache(self):
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.cache_data, f)
        except Exception as e:
            print(f" [MACRO CACHE] Failed to save cache: {e}")

    async def sync_cache(self, symbols: List[str] = None):
        if self.is_syncing:
            return {"status": "already_syncing"}
        self.is_syncing = True
        try:
            from app.services.kite_data import kite_data
            if not kite_data.is_ready:
                await kite_data.initialize()
            if not kite_data.is_ready:
                print(" [MACRO CACHE] Kite is not ready, cannot sync macro cache")
                return {"status": "error", "message": "Kite not ready"}

            if symbols is None:
                from app.services.market_discovery import market_discovery
                symbols_list = await market_discovery.get_full_market_list()
                symbols = [s["symbol"] if isinstance(s, dict) else s for s in symbols_list]

            print(f" [MACRO CACHE] Starting sync for {len(symbols)} symbols...")
            for i, sym in enumerate(symbols):
                try:
                    # 1D Data (3 months)
                    res_1d = await kite_data.fetch_batch([sym], interval="1d", period="3mo")
                    if sym in res_1d and not res_1d[sym].empty:
                        # Convert datetime index to string for JSON serialization
                        df_json = res_1d[sym].reset_index().to_dict(orient="records")
                        # Format datetime safely
                        for row in df_json:
                            if 'date' in row and pd.notnull(row['date']):
                                row['date'] = str(row['date'])
                        self.cache_data["1d"][sym] = df_json

                    await asyncio.sleep(0.35)  # Strict Kite Rate Limit: 3 req/sec

                    # 60m Data (15 days)
                    res_60m = await kite_data.fetch_batch([sym], interval="60m", period="15d")
                    if sym in res_60m and not res_60m[sym].empty:
                        df_json = res_60m[sym].reset_index().to_dict(orient="records")
                        for row in df_json:
                            if 'date' in row and pd.notnull(row['date']):
                                row['date'] = str(row['date'])
                        self.cache_data["60m"][sym] = df_json

                    await asyncio.sleep(0.35)

                    if (i + 1) % 50 == 0:
                        print(f" [MACRO CACHE] Synced {i + 1}/{len(symbols)}...")
                        self._save_cache()

                except Exception as e:
                    print(f" [MACRO CACHE] Failed to sync {sym}: {e}")

            self.cache_data["last_updated"] = time.time()
            self._save_cache()
            print(" [MACRO CACHE] Sync completed successfully.")
            return {"status": "success"}
        finally:
            self.is_syncing = False

    def get_1d_data(self, symbol: str) -> pd.DataFrame:
        data = self.cache_data["1d"].get(symbol)
        if not data:
            return None
        try:
            df = pd.DataFrame(data)
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            return df
        except:
            return None

    def get_60m_data(self, symbol: str) -> pd.DataFrame:
        data = self.cache_data["60m"].get(symbol)
        if not data:
            return None
        try:
            df = pd.DataFrame(data)
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df.set_index('date', inplace=True)
            return df
        except:
            return None

macro_cache = MacroCacheService()
