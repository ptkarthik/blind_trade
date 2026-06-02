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
from datetime import datetime
from app.services.kite_data import kite_data

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
        # Initialize Kite Connect (loads saved session or prompts login)
        await kite_data.initialize()
        kite_status = "CONNECTED" if kite_data.is_ready else "FALLBACK (Yahoo)"
        print(f" MarketDataService: Systems Online ({len(self.stock_master)} symbols). Data: {kite_status}")

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
        
        # Load dynamic industry data from cache if available
        import json, os
        cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nse_market_list.json")
        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    stocks = json.load(f)
                for s in stocks:
                    raw = s.get("raw_symbol", "").upper()
                    industry = s.get("industry", "General")
                    if raw and industry != "General":
                        self.SECTOR_MAP[raw] = industry
            except Exception:
                pass

        self.INDEX_MAP = {
            "Banking": "^NSEBANK", "IT": "^CNXIT", "Auto": "^CNXAUTO", "Energy": "^CNXENERGY",
            "FMCG": "^CNXFMCG", "Infrastructure": "^CNXINFRA", "Pharma": "^CNXPHARMA", "Metal": "^CNXMETAL"
        }

    async def search_symbols(self, query: str) -> list:
        """[KITE UPGRADE] Search for stocks using Kite's active instrument list."""
        if not query: return []
        q = query.upper()
        results = []
        
        try:
            if kite_data.is_ready and hasattr(kite_data, '_instruments'):
                for sym in kite_data._instruments.keys():
                    if q in sym:
                        results.append({
                            "symbol": f"{sym}.NS",
                            "name": sym,
                            "sector": self.SECTOR_MAP.get(sym, "General")
                        })
                        if len(results) >= 15:
                            break
                if results:
                    return results
        except Exception as e:
            print(f"️ [SEARCH] Kite search failed: {e}")
            
        # Fallback
        for item in self.stock_master:
            name_val = item.get("name", "")
            sym_val = item.get("symbol", "")
            if q in sym_val.upper() or q in name_val.upper():
                results.append(item)
                if len(results) >= 15:
                    break
        return results

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
        """[V12.2 REPAIRED] High-Velocity Concurrent Pulse Loader.
        
        [KITE UPGRADE] Tries Kite Connect first for historical data,
        then falls back to Yahoo Fast for any symbols that failed.
        """
        results = {}
        remaining_symbols = list(symbols)
        
        # ── TIER 1: Kite Connect (Primary — only for small batches) ──
        # Kite Historical API = 3 req/sec → 1,300 symbols = ~7 min (SLOW)
        # Yahoo batch = 10 parallel = ~3 min for same (FASTER for bulk)
        # Use Kite only for ≤50 symbols (index context, re-scans, paper monitor)
        if kite_data.is_ready and len(symbols) <= 50:
            try:
                kite_results = await kite_data.fetch_batch(remaining_symbols, interval=interval, period=period)
                if kite_results:
                    results.update(kite_results)
                    remaining_symbols = [s for s in remaining_symbols if s not in kite_results]
                    if len(kite_results) > 0:
                        print(f" [DATA SOURCE] Fetched Historical OHLC for {len(kite_results)} symbols from KITE")
            except Exception as e:
                print(f"️ [KITE] Batch fetch failed, falling back to Yahoo: {e}")
        
        # ── TIER 2: Yahoo Fast (Fallback for failures) ──
        if remaining_symbols:
            batch_size = 60
            concurrent_batches = 2
            all_chunks = [remaining_symbols[i:i + batch_size] for i in range(0, len(remaining_symbols), batch_size)]
            
            for i in range(0, len(all_chunks), concurrent_batches):
                group = all_chunks[i:i + concurrent_batches]
                
                async def _process_chunk(chunk):
                    batch_results = {}
                    proxy = await proxy_manager.get_proxy()
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    
                    from app.services.yahoo_fast import yahoo_fast
                    try:
                        batch_results = await yahoo_fast.fetch_batch(chunk, interval=interval, period=period, concurrency=10)
                        
                        if not batch_results and self.td and i == 0:
                            # [V12.5 FIX] TwelveData has 8 req/min limit. Do not use for bulk failover, it hangs the system.
                            if len(chunk) <= 5:
                                print(f" [YAHOO BLOCKED] Invoking TwelveData Failover for small batch...")
                                async def _td_fallback(s):
                                    try:
                                        def _fetch_td():
                                            return self.td.time_series(symbol=s, interval=interval, outputsize=50).as_pandas()
                                        td_df = await asyncio.to_thread(_fetch_td)
                                        if not td_df.empty:
                                            td_df.columns = [c.lower() for c in td_df.columns]
                                            return s, td_df
                                    except Exception as e:
                                        print(f" [TD FAILOVER] {s}: {e}")
                                    return s, None
                                    
                                td_results = await asyncio.gather(*[_td_fallback(s) for s in chunk])
                                for s, df in td_results:
                                    if df is not None:
                                        batch_results[s] = df
                            else:
                                print(f" [YAHOO BLOCKED] Batch too large for TwelveData failover ({len(chunk)}). Skipping failover.")
                        
                        return batch_results
                    except Exception as e:
                        print(f" [API FAIL] Batch fetch failed. Error: {str(e)}")
                        import traceback
                        traceback.print_exc()
                        return {}

                pulse_tasks = [_process_chunk(chunk) for chunk in group]
                batch_outputs = await asyncio.gather(*pulse_tasks)
                
                for b_res in batch_outputs:
                    results.update(b_res)
                    if b_res:
                        print(f" [DATA SOURCE] Fetched Historical OHLC for {len(b_res)} symbols from YAHOO")
                
                await asyncio.sleep(1.5)
            
        return results

    async def get_batch_prices(self, symbols: list[str]) -> Dict[str, Dict[str, Any]]:
        """[V12 REPAIRED] High-Velocity Price Pulse.
        
        [KITE UPGRADE] Uses Kite LTP API for instant bulk quotes,
        falls back to Yahoo yf.download for failures.
        """
        results = {}
        remaining = list(symbols)
        
        # ── TIER 1: Kite LTP (Primary — instant bulk quotes) ──
        if kite_data.is_ready:
            try:
                kite_prices = await kite_data.get_ltp(symbols)
                if kite_prices:
                    results.update(kite_prices)
                    remaining = [s for s in symbols if s not in kite_prices]
                    print(f" [DATA SOURCE] Fetched Live Prices (LTP) for {len(kite_prices)} symbols from KITE")
            except Exception as e:
                print(f"️ [KITE] LTP fetch failed: {e}")
        
        # ── TIER 2: Yahoo (Fallback) ──
        if remaining:
            batch_size = 150
            for i in range(0, len(remaining), batch_size):
                chunk = remaining[i:i + batch_size]
                proxy = await proxy_manager.get_proxy()
                try:
                    def _batch(): 
                        return yf.download(
                            chunk, period="1d", interval="15m", 
                            group_by='ticker', progress=False, threads=True, 
                            proxy=proxy, session=self.session, timeout=15
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
                    if results:
                        print(f" [DATA SOURCE] Fetched Live Prices for {len(chunk)} symbols from YAHOO")
                    await asyncio.sleep(0.3)
                except: continue
        return results

    async def get_advance_decline_ratio(self) -> float:
        """[V18 FIX #11] Professional A/D Ratio with 30-stock sample for statistical significance.
        
        [KITE UPGRADE] Uses Kite bulk LTP for instant, reliable breadth signal.
        """
        try:
            nifty_sample = [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
                "HUL.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "KOTAKBANK.NS",
                "LT.NS", "AXISBANK.NS", "ASIANPAINT.NS", "MARUTI.NS", "TITAN.NS",
                "SUNPHARMA.NS", "BAJFINANCE.NS", "WIPRO.NS", "ULTRACEMCO.NS", "NESTLEIND.NS",
                "TATASTEEL.NS", "POWERGRID.NS", "NTPC.NS", "ONGC.NS", "JSWSTEEL.NS",
                "M&M.NS", "TATAMOTORS.NS", "ADANIENT.NS", "TECHM.NS", "HCLTECH.NS"
            ]
            prices = await self.get_batch_prices(nifty_sample)
            # Only count stocks that returned valid price data
            valid_prices = {k: v for k, v in prices.items() if v.get("price", 0) > 0}
            if len(valid_prices) < 10:
                return 1.0
            adv = sum(1 for p in valid_prices.values() if p.get("change_percent", 0) > 0)
            dec = len(valid_prices) - adv
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

    def get_name_for_symbol(self, symbol: str) -> str:
        """Returns a human-readable company name from the cached NSE market list.
        Falls back to cleaned symbol if not found. Never makes a network call."""
        import os, json
        try:
            cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nse_market_list.json")
            if os.path.exists(cache_path):
                with open(cache_path, "r") as f:
                    stocks = json.load(f)
                for stock in stocks:
                    if stock.get("symbol") == symbol:
                        return stock.get("name", symbol.split(".")[0])
        except Exception:
            pass
        return symbol.split(".")[0]

    async def _fetch_live_with_proxy(self, symbol: str) -> Dict[str, Any]:
        proxy = await proxy_manager.get_proxy()
        if not proxy: return {"price": 0, "source": "Failed"}
        try:
            def _try():
                t = yf.Ticker(symbol)
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
            is_weekday = ist_now.weekday() < 5
            current_time = ist_now.strftime("%H:%M")
            status = "OPEN" if is_weekday and "09:15" <= current_time <= "15:30" else "CLOSED"
            return {
                "status": status,
                "nifty_50": ctx.get("price", 0.0),
                "nifty_change": ctx.get("change_percent", 0.0),
                "india_vix": round(vix_val, 2),
                "timestamp": time.time()
            }
        except Exception as e: 
            print(f"️ [MARKET_STATUS] Failed to fetch: {e}")
            return {"status": "OPEN", "nifty_50": 0.0, "india_vix": 15.0}

    async def get_ohlc(self, symbol: str, period: str = "30d", interval: str = "1d", fast_fail: bool=False):
        """[KITE UPGRADE] Single-symbol OHLC with Kite-first fallback chain."""
        # ── TIER 1: Kite Connect ──
        if kite_data.is_ready:
            try:
                df = await kite_data.fetch_ohlc(symbol, period=period, interval=interval)
                if not df.empty:
                    return df
            except Exception:
                pass

        # ── TIER 2: Yahoo Direct ──
        proxy = await proxy_manager.get_proxy()
        try:
            def _fetch(): 
                return yf.Ticker(symbol).history(period=period, interval=interval)
            df = await asyncio.to_thread(_fetch)
            if df is not None and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception as e:
            print(f"[OHLC] Direct Yahoo fetch failed for {symbol}: {e}")
        
        # ── TIER 3: TwelveData ──
        if self.td:
            try:
                td_df = self.td.time_series(symbol=symbol, interval=interval, outputsize=50).as_pandas()
                if not td_df.empty:
                    td_df.columns = [c.lower() for c in td_df.columns]
                    return td_df
            except Exception as e:
                print(f"[OHLC] TwelveData failover also failed for {symbol}: {e}")
            
        return pd.DataFrame()

market_service = MarketDataService()
