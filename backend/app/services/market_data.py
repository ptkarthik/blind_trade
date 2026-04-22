import yfinance as yf
try:
    from yfinance.exceptions import YFRateLimitError, YFDataException
except ImportError:
    class YFRateLimitError(Exception): pass
    class YFDataException(Exception): pass

from app.services.proxy_manager import proxy_manager
import pandas as pd
from typing import Dict, Any, List
import asyncio
import random
from app.core.config import settings
from twelvedata import TDClient
import time
import urllib3
import traceback
import numpy as np

# Suppress InsecureRequestWarning for proxies
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class MarketDataService:
    def __init__(self):
        # Professional Data Providers
        self.td = TDClient(apikey=settings.MARKET_DATA_API_KEY) if settings.MARKET_DATA_API_KEY else None
        self.td_disabled = False 
        self.td_credit_count = 0 
        
        # Cache Config
        self.price_cache = {}
        self.index_cache = {}
        self.ohlc_cache = {}
        self.financials_cache = {}
        self.CACHE_DURATION = 10 
        self.INDEX_CACHE_DURATION = 60 
        
        self.stock_master = []
        self._init_session()
        self._load_sector_maps()

    async def initialize(self):
        """[V11 RESTORED] Async Initialization Pulse."""
        self._load_master_list()
        print(f"📦 MarketDataService: Systems Online ({len(self.stock_master)} symbols).")

    def _load_master_list(self):
        """[V11 RESTORED] Loads Nifty 500+ Universe."""
        import json
        import os
        added = set()
        # 1. Base Symbols
        for sym, sec in self.SECTOR_MAP.items():
            fs = sym if "." in sym else f"{sym}.NS"
            self.stock_master.append({"symbol": fs, "sector": sec})
            added.add(sym.upper())

        # 2. Expanded Universe
        dp = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "nifty500.json")
        if os.path.exists(dp):
            try:
                with open(dp, "r") as f:
                    exp = json.load(f)
                    for item in exp:
                        rs = item["symbol"].split(".")[0].upper()
                        if rs not in added:
                            self.stock_master.append(item)
                            added.add(rs)
            except: pass

    def _init_session(self):
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        self.session = requests.Session()
        # [V21.2 FIX] Enforce strict SSL validation. If proxies fail SSL, they are unsafe.
        self.session.verify = True 
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Connection": "keep-alive"
        })
        retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _load_sector_maps(self):
        self.SECTOR_MAP = {
            "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "KOTAKBANK": "Banking", "AXISBANK": "Banking",
            "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT",
            "TATAMOTORS": "Auto", "MARUTI": "Auto", "M&M": "Auto", "EICHERMOT": "Auto", "BAJAJ-AUTO": "Auto",
            "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Energy", "POWERGRID": "Energy", "COALINDIA": "Energy",
            "HUL": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG", "TITAN": "FMCG",
            "LT": "Infrastructure", "ADANIENT": "Infrastructure", "ADANIPORTS": "Infrastructure", "ULTRACEMCO": "Infrastructure",
            "PHAR": "Pharma", "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
            "METAL": "Metal", "TATASTEEL": "Metal", "JSWSTEEL": "Metal", "HINDALCO": "Metal"
        }
        self.INDEX_MAP = {
            "Banking": "^NSEBANK", "IT": "^CNXIT", "Auto": "^CNXAUTO", "Energy": "^CNXENERGY",
            "FMCG": "^CNXFMCG", "Infrastructure": "^CNXINFRA", "Pharma": "^CNXPHARMA", "Metal": "^CNXMETAL"
        }

    async def get_live_price(self, symbol: str) -> Dict[str, Any]:
        """[V11 RESTORED] Credit-Aware Price Fetcher."""
        current_time = time.time()
        if symbol in self.price_cache:
            entry = self.price_cache[symbol]
            if current_time - entry["timestamp"] < self.CACHE_DURATION:
                return entry["data"]

        # Restore TwelveData Pulse (8 credits per minute limit)
        if self.td and not self.td_disabled and self.td_credit_count < 8:
            try:
                def _td_fetch():
                    ts = self.td.time_series(symbol=symbol, interval="1min", outputsize=1)
                    return ts.as_json()[0]
                data = await asyncio.to_thread(_td_fetch)
                self.td_credit_count += 1
                res = {
                    "symbol": symbol, "price": float(data['close']), 
                    "change_percent": 0.0, "source": "TwelveData"
                }
                self.price_cache[symbol] = {"timestamp": current_time, "data": res}
                return res
            except:
                self.td_disabled = True # Fallback on error

        # Yahoo Direct Fallback
        try:
            def _yf_fetch():
                t = yf.Ticker(symbol)
                h = t.history(period="1d")
                return {"price": h['Close'].iloc[-1], "open": h['Open'].iloc[0]}
            data = await asyncio.to_thread(_yf_fetch)
            p, pc = data['price'], data['open']
            res = {
                "symbol": symbol, "price": round(p, 2), "change": round(p-pc, 2),
                "change_percent": round(((p-pc)/pc)*100 if pc else 0, 2), "source": "Yahoo"
            }
            self.price_cache[symbol] = {"timestamp": current_time, "data": res}
            return res
        except:
            return await self._fetch_live_with_proxy(symbol)

    async def get_batch_ohlc(self, symbols: list[str], period: str = "7d", interval: str = "15m") -> Dict[str, pd.DataFrame]:
        """[V12.2 REPAIRED] High-Velocity Concurrent Pulse Loader."""
        results = {}
        batch_size = 60 # Increased from 30 for higher throughput
        concurrent_batches = 2 # Increased from 1 to allow some parallel sub-batches
        
        all_chunks = [symbols[i:i + batch_size] for i in range(0, len(symbols), batch_size)]
        
        for i in range(0, len(all_chunks), concurrent_batches):
            group = all_chunks[i:i + concurrent_batches]
            
            async def _process_chunk(chunk):
                batch_results = {}
                proxy = await proxy_manager.get_proxy()
                # Faster Humanize: Reduced from 1.0-3.0 to 0.2-0.5 for Grow Plan performance
                await asyncio.sleep(random.uniform(0.2, 0.5))
                
                # [V12.4 HYPER-SPEED RESTORATION] 🚀
                from app.services.yahoo_fast import yahoo_fast
                try:
                    # Mimic the 'Sequential 5 symbols a second' logic by using Parallel Ribbons
                    batch_results = await yahoo_fast.fetch_batch(chunk, interval=interval, period=period, concurrency=10)
                    
                    if not batch_results and self.td and i == 0:
                        # TwelveData as last resort for Nifty 50 only
                        print(f"🆘 [YAHOO BLOCKED] Invoking TwelveData Failover for batch...")
                        for s in chunk:
                            try:
                                td_df = self.td.time_series(symbol=s, interval=interval, outputsize=50).as_pandas()
                                if not td_df.empty:
                                    td_df.columns = [c.lower() for c in td_df.columns]
                                    batch_results[s] = td_df
                            except Exception as e:
                                print(f"⚠️ [TD FAILOVER] {s}: {e}")
                                continue
                    
                    return batch_results
                except Exception as e:
                    print(f"❌ [API FAIL] Batch fetch failed. Error: {str(e)}")
                    # V21.2 FIX: Don't just return {} silently. Log the failure explicitly.
                    import traceback
                    traceback.print_exc()
                    return {}

            # Fire batches in the current group concurrently (now limited to 1)
            pulse_tasks = [_process_chunk(chunk) for chunk in group]
            batch_outputs = await asyncio.gather(*pulse_tasks)
            
            for b_res in batch_outputs:
                results.update(b_res)
            
            # [V12.2 GUARD] Balanced delay between batches
            await asyncio.sleep(1.5) 
            
        return results

    async def get_batch_prices(self, symbols: list[str]) -> Dict[str, Dict[str, Any]]:
        """[V12 REPAIRED] High-Velocity Price Pulse."""
        results = {}
        batch_size = 150
        for i in range(0, len(symbols), batch_size):
            chunk = symbols[i:i + batch_size]
            proxy = await proxy_manager.get_proxy()
            try:
                def _batch(): 
                    return yf.download(
                        chunk, period="1d", interval="15m", 
                        group_by='ticker', progress=False, threads=True, 
                        proxy=proxy, session=self.session
                    )
                df_batch = await asyncio.to_thread(_batch)
                for s in chunk:
                    try:
                        if isinstance(df_batch.columns, pd.MultiIndex):
                            sdf = df_batch[s] if s in df_batch.columns.levels[0] else None
                        else: sdf = df_batch
                        
                        if sdf is not None and not sdf.empty:
                            p = float(sdf['Close'].iloc[-1])
                            op = float(sdf['Open'].iloc[0])
                            results[s] = {"price": p, "change_percent": round(((p-op)/op)*100 if op else 0, 2)}
                    except: continue
                await asyncio.sleep(0.3) # Faster guard for price pulse
            except: continue
        return results

    async def get_advance_decline_ratio(self) -> float:
        """[V18 FIX #11] Professional A/D Ratio with 30-stock sample for statistical significance."""
        try:
            # Expanded from 8 to 30 Nifty 50 components for reliable breadth signal
            nifty_sample = [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
                "HUL.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
                "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
                "SUNPHARMA.NS", "BAJFINANCE.NS", "WIPRO.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
                "TATASTEEL.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "JSWSTEEL.NS",
                "M&M.NS", "TATAMOTORS.NS", "ADANIENT.NS", "TECHM.NS", "HCLTECH.NS"
            ]
            prices = await self.get_batch_prices(nifty_sample)
            adv = sum(1 for p in prices.values() if p.get("change_percent", 0) > 0)
            dec = len(prices) - adv
            return adv / max(dec, 1)
        except: return 1.0

    async def get_sector_performances(self) -> Dict[str, float]:
        """[V17 Optimized] Sector Heatmap Pulse via YahooFast."""
        from app.services.yahoo_fast import yahoo_fast
        sectors = list(self.INDEX_MAP.values())
        
        # Fetching 2 days to calculate % change accurately from previous close
        results = await yahoo_fast.fetch_batch(sectors, interval="1d", period="5d")
        
        perf = {}
        for s_name, ticker in self.INDEX_MAP.items():
            df = results.get(ticker)
            if df is not None and len(df) >= 2:
                p_close = df['close'].iloc[-2]
                curr = df['close'].iloc[-1]
                chg = ((curr - p_close) / p_close) * 100 if p_close != 0 else 0
                perf[s_name] = round(chg, 2)
            else:
                perf[s_name] = 0.0
        return perf

    def get_sector_for_symbol(self, symbol: str) -> str:
        clean = symbol.split(".")[0].upper()
        return self.SECTOR_MAP.get(clean, "General")

    async def _fetch_live_with_proxy(self, symbol: str) -> Dict[str, Any]:
        proxy = await proxy_manager.get_proxy()
        if not proxy: return {"price": 0, "source": "Failed"}
        try:
            def _try():
                t = yf.Ticker(symbol, proxy=proxy)
                h = t.history(period="1d")
                return h['Close'].iloc[-1]
            p = await asyncio.to_thread(_try)
            return {"symbol": symbol, "price": p, "source": "Yahoo Proxy"}
        except: return {"price": 0, "source": "Proxy Failed"}

    async def get_market_status(self) -> Dict[str, Any]:
        """[V11 RESTORED] Dashboard Heartbeat: Nifty 50 + Market State."""
        try:
            # Check price of Nifty Index
            ctx = await self.get_live_price("^NSEI")
            
            # [V14] Real-time VIX Pulse
            vix_ctx = await self.get_live_price("^INDIAVIX")
            vix_val = vix_ctx.get("price", 15.0)
            
            # [V18 FIX #10] Use IST timezone, not server local time
            import pytz
            ist_now = datetime.now(pytz.timezone('Asia/Kolkata'))
            status = "OPEN" if ist_now.strftime("%H:%M") < "15:35" else "CLOSED"
            return {
                "status": status,
                "nifty_50": ctx.get("price", 0.0),
                "nifty_change": ctx.get("change_percent", 0.0),
                "india_vix": round(vix_val, 2),
                "timestamp": time.time()
            }
        except Exception as e: 
            print(f"⚠️ [MARKET_STATUS] Failed to fetch: {e}")
            return {"status": "OPEN", "nifty_50": 0.0, "india_vix": 15.0}

    async def get_ohlc(self, symbol: str, period: str = "30d", interval: str = "1d", fast_fail: bool=False):
        proxy = await proxy_manager.get_proxy()
        try:
            def _fetch(): 
                return yf.Ticker(symbol, proxy=proxy, session=self.session).history(period=period, interval=interval)
            df = await asyncio.to_thread(_fetch)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception as e:
            print(f"⚠️ [OHLC] Direct Yahoo fetch failed for {symbol}: {e}")
        
        # [V12.3 SINGLE FAILOVER] 🆘
        if self.td:
            try:
                td_df = self.td.time_series(symbol=symbol, interval=interval, outputsize=50).as_pandas()
                if not td_df.empty:
                    td_df.columns = [c.lower() for c in td_df.columns]
                    return td_df
            except Exception as e:
                print(f"⚠️ [OHLC] TwelveData failover also failed for {symbol}: {e}")
            
        return pd.DataFrame()

market_service = MarketDataService()
