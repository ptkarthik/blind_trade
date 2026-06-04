import yfinance as yf
try:
    from yfinance.exceptions import YFRateLimitError, YFDataException
except ImportError:
    # Handle older yfinance versions
    class YFRateLimitError(Exception): pass
    class YFDataException(Exception): pass

from app.services.proxy_manager import proxy_manager
import pandas as pd
from typing import Dict, Any
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

from app.services.market_discovery import market_discovery

class MarketDataService:
    async def _async_retry(self, func, *args, max_retries=3, initial_backoff=1, **kwargs):
        """Helper for exponential backoff retries with specific rate limit handling."""
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except YFRateLimitError:
                # Specific handling for yfinance rate limits
                backoff = initial_backoff * (4 ** attempt) + random.uniform(1, 3)
                print(f"️ YF Rate Limit hit. Backing off for {round(backoff, 2)}s (Attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(backoff)
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                backoff = initial_backoff * (2 ** attempt) + random.uniform(0, 1)
                await asyncio.sleep(backoff)
        return None
    def __init__(self):
        # Cache Config
        self.price_cache = {}
        self.index_cache = {}
        self.ohlc_cache = {} # Phase 65: OHLC Caching
        self.financials_cache = {}
        self.extended_data_cache = {}
        self.CACHE_DURATION = 10 # seconds generic price
        self.INDEX_CACHE_DURATION = 60 # Phase 97: 60s for Index Status (faster polling)
        self.OHLC_CACHE_DURATION = 300 # 5 minutes for OHLC
        self.EXTENDED_CACHE_DURATION = 3600 * 24 

        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/10.15.7',
            'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0'
        ]
        
        # Standard Session

        self._init_session()

    def _init_session(self):
        """Standard requests session for secondary APIs and yfinance."""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # 1. Standard Session for custom API calls
        self.session = requests.Session()
        self.session.trust_env = True
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        # Phase 97: yfinance handles its own session (now requires curl_cffi in some envs)
        # We stop passing a custom session to avoid "curl_cffi" requirement errors.
        

        # Static Sector Mapping (Expanded Universe: Large, Mid, Small)
        self.SECTOR_MAP = {
            # --- BANKING ---
            "HDFCBANK": "Banking", "ICICIBANK": "Banking", "SBIN": "Banking", "KOTAKBANK": "Banking", "AXISBANK": "Banking",
            "INDUSINDBK": "Banking", "BANKBARODA": "Banking", "PNB": "Banking", # Large
            "IDFCFIRSTB": "Banking", "AUBANK": "Banking", "FEDERALBNK": "Banking", "BANDHANBNK": "Banking", # Mid
            "RBLBANK": "Banking", "KARURVYSYA": "Banking", "CITYUNION": "Banking", "UCOBANK": "Banking", "MAHABANK": "Banking", "YESBANK": "Banking", # Small/Mid

            # --- IT ---
            "TCS": "IT", "INFY": "IT", "HCLTECH": "IT", "WIPRO": "IT", "TECHM": "IT", # Large
            "LTIM": "IT", "PERSISTENT": "IT", "COFORGE": "IT", "MPHASIS": "IT", "TATAELXSI": "IT", # Mid
            "KPITTECH": "IT", "CYIENT": "IT", "ZENSARTECH": "IT", "BSOFT": "IT", "SONATSOFTW": "IT", # Small/Mid

            # --- AUTO ---
            "TATAMOTORS": "Auto", "MARUTI": "Auto", "M&M": "Auto", "EICHERMOT": "Auto", "BAJAJ-AUTO": "Auto", # Large
            "TVSMOTOR": "Auto", "HEROMOTOCO": "Auto", "TIINDIA": "Auto", "BHARATFORG": "Auto", "ASHOKLEY": "Auto", # Mid
            "APOLLOTYRE": "Auto", "EXIDEIND": "Auto", "AMARAJABAT": "Auto", "CEATLTD": "Auto", "MOTHERSON": "Auto", # Small/Mid

            # --- PHARMA ---
            "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma", "DIVISLAB": "Pharma", "APOLLOHOSP": "Pharma", # Large
            "LUPIN": "Pharma", "ALKEM": "Pharma", "TORNTPHARM": "Pharma", "AUROPHARMA": "Pharma", "BIOCON": "Pharma", # Mid
            "LAURUSLAB": "Pharma", "GRANULES": "Pharma", "GLENMARK": "Pharma", "JBCHEPHARM": "Pharma", "NATCOPHARM": "Pharma", # Small

            # --- ENERGY / POWER ---
            "RELIANCE": "Energy", "ONGC": "Energy", "NTPC": "Energy", "POWERGRID": "Energy", "COALINDIA": "Energy", # Large
            "TATAPOWER": "Energy", "ADANIGREEN": "Energy", "ADANIPOWER": "Energy", "JSWENERGY": "Energy", "NHPC": "Energy", # Mid
            "SJVN": "Energy", "SUZLON": "Energy", "INOXWIND": "Energy", "IEX": "Energy", "CESC": "Energy", # Small

            # --- FMCG ---
            "HUL": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG", "BRITANNIA": "FMCG", "TITAN": "FMCG", # Large
            "ASIANPAINT": "FMCG", "GODREJCP": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG", "COLPAL": "FMCG", # Mid
            "VARUNBEV": "FMCG", "UBL": "FMCG", "RADICO": "FMCG", "RENUKA": "FMCG", "TRIDENT": "FMCG", # Small/Mid

            # --- METAL ---
            "TATASTEEL": "Metal", "JSWSTEEL": "Metal", "HINDALCO": "Metal", "VEDL": "Metal", "JINDALSTEL": "Metal", # Large
            "NMDC": "Metal", "SAIL": "Metal", "APLAPOLLO": "Metal", "NATIONALUM": "Metal", "HINDZINC": "Metal", # Mid
            "WELCORP": "Metal", "JSL": "Metal", "RATNAMANI": "Metal", "HCG": "Metal", # Small

            # --- INFRA / CAPITAL GOODS ---
            "LT": "Infrastructure", "ADANIENT": "Infrastructure", "ADANIPORTS": "Infrastructure", "ULTRACEMCO": "Infrastructure", # Large
            "HAL": "Infrastructure", "BEL": "Infrastructure", "SIEMENS": "Infrastructure", "ABB": "Infrastructure", "INDIGO": "Infrastructure", # Mid/Large
            "RVNL": "Infrastructure", "IRFC": "Infrastructure", "MAZDOCK": "Infrastructure", "NBCC": "Infrastructure", "HUDCO": "Infrastructure", # PSU/Mid
            "GMRINFRA": "Infrastructure", "IRB": "Infrastructure", "ENGINEERSIN": "Infrastructure", # Small

            # --- REALTY ---
            "DLF": "Realty", "GODREJPROP": "Realty", "LODHA": "Realty", "PHOENIXLTD": "Realty", "OBEROIRLTY": "Realty", # Large/Mid
            "PRESTIGE": "Realty", "BRIGADE": "Realty", "SOBHA": "Realty", "IBREALEST": "Realty", # Small

            # --- SERVICES / NEW AGE ---
            "ZOMATO": "Services", "PAYTM": "Services", "NAUKRI": "Services", "POLICYBZR": "Services", "DELHIVERY": "Services",
            "NYKAA": "Services", "IDEA": "Services", "TRENT": "Services", "JUBLFOOD": "Services", "DEVYANI": "Services"
        }
        
        # Sector to Index Mapping (Phase 30)
        self.INDEX_MAP = {
            "Banking": "^NSEBANK",
            "IT": "^CNXIT",
            "Auto": "^CNXAUTO",
            "Pharma": "^CNXPHARMA",
            "Energy": "^CNXENERGY",
            "FMCG": "^CNXFMCG",
            "Metal": "^CNXMETAL",
            "Infrastructure": "^CNXINFRA",
            "Realty": "^CNXREALTY",
            "Financial Services": "^CNXFIN",
            "Services": "^NSEI" # Default to Nifty 50
        }

        # Static Master List for Fallback (Populate from SECTOR_MAP)
        self.stock_master = []
        self._load_master_list()

        # Metadata Cache (Phase 52)
        self.metadata_cache = {}
        self._load_metadata_cache()

        # Circuit Breaker for TwelveData (Permanent Disable if limit hit)
        self.td_disabled = False
        self.td_disabled_until = 0 # Timestamp for cooldown

        # Initialize TwelveData client if key is available
        self.td = None
        if settings.MARKET_DATA_API_KEY and "your_twelvedata" not in settings.MARKET_DATA_API_KEY:
            try:
                self.td = TDClient(apikey=settings.MARKET_DATA_API_KEY)
                print("MarketDataService: Professional API (TwelveData) Enabled.")
            except Exception as e:
                err_msg = str(e)
                err_preview = (err_msg[:100] + "...") if len(err_msg) > 100 else err_msg
                print(f"️ TwelveData Client Init Failed (Outage?): {err_preview}")
                print("Falling back to Community API (Yahoo Finance).")
                self.td = None
                self.td_disabled = True
                self.td_disabled_until = time.time() + 3600 # 1 hour cooldown
        else:
            print("MarketDataService: Using Community API (Yahoo Finance) + Mock Fallback.")

    def _load_master_list(self):
        """
        Loads the expanded universe from nifty500.json if available.
        Otherwise falls back to the static SECTOR_MAP.
        """
        import json
        import os
        
        # 1. Start with static map (Normalize to .NS if no suffix)
        added_raw = set()
        for sym, sec in self.SECTOR_MAP.items():
             full_sym = sym if "." in sym else f"{sym}.NS"
             self.stock_master.append({"symbol": full_sym, "name": sym, "sector": sec})
             added_raw.add(sym.upper())
             
        # 2. Try to load expanded universe
        data_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "nifty500.json")
        if os.path.exists(data_path):
            try:
                with open(data_path, "r") as f:
                    expanded = json.load(f)
                    for item in expanded:
                        raw_sym = item["symbol"].split(".")[0].upper()
                        if raw_sym not in added_raw:
                            self.stock_master.append(item)
                            added_raw.add(raw_sym)
            except Exception as e:
                print(f"MarketDataService: Failed to load expanded universe: {e}")

        # 3. Dynamic Full Discovery (NSE EQUITY_L)
        try:
             # We fetch this asynchronously later or just-in-time if needed
             # For now, we keep stock_master as the 'fast' list, but engines can request 'all'
             pass
        except: pass

        print(f"MarketDataService: Initialized with {len(self.stock_master)} base symbols.")


    def _load_metadata_cache(self):
        """Loads metadata (sector/cap) from local JSON to avoid re-fetching."""
        import json
        import os
        cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "metadata_cache.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    self.metadata_cache = json.load(f)
                print(f"MarketData: Loaded metadata cache for {len(self.metadata_cache)} stocks.")
            except:
                self.metadata_cache = {}
                print(f"Error loading metadata cache. Initializing empty cache.")

    def _save_metadata_cache(self):
        """Saves current metadata cache to disk."""
        import json
        import os
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(cache_dir, "metadata_cache.json")
        try:
            with open(cache_file, "w") as f:
                json.dump(self.metadata_cache, f, indent=4)
        except Exception as e:
            print(f"Error saving metadata cache: {e}")

    async def initialize(self):
        """
        Initialize using the static master list and Cache.
        """
        print(f"Initializing Market Data Service...")
        print(f"Loaded {len(self.stock_master)} stocks from Expanded Universe.")
        print(f"Market Data Initialized. Cache Size: {len(self.metadata_cache)}")

    async def search_symbols(self, query: str) -> list:
        """
        Search for symbols/names matching the query.
        Checks both static master and metadata cache (dynamic symbols).
        """
        if not query: return []
        q = query.upper()
        results = []
        
        # 1. Search in static master
        for item in self.stock_master:
            if q in item["symbol"] or q in item["name"].upper():
                results.append(item)
                
        # 2. Search in metadata cache
        for sym, meta in self.metadata_cache.items():
            if q in sym:
                if not any(r["symbol"] == sym for r in results):
                    results.append({"symbol": sym, "name": sym, "sector": meta.get("sector", "Unknown")})
                    
        return results[:10]

    async def get_symbol_metadata(self, symbol: str) -> Dict[str, Any]:
        """
        Returns sector and market cap category for a symbol, using cache or fetching live.
        """
        if symbol in self.metadata_cache:
            return self.metadata_cache[symbol]
        
        # Check static map first
        if symbol in self.SECTOR_MAP:
            data = {"sector": self.SECTOR_MAP[symbol], "market_cap": "Large"} 
            self.metadata_cache[symbol] = data
            return data

        # Check stock master (Nifty 500)
        clean_sym = symbol.split(".")[0].upper()
        for item in self.stock_master:
            if item["symbol"].split(".")[0].upper() == clean_sym:
                 data = {
                     "sector": item.get("sector", "General"),
                     "market_cap": "Mid" # Default/approx since JSON might not have cap
                 }
                 self.metadata_cache[symbol] = data
                 return data
            
        print(f" Metadata Fetch for {symbol}...")
        info = await self.get_fundamentals(symbol)
        
        sector = info.get("sector", "General")
        mkt_cap = info.get("marketCap", 0)
        
        # Category Logic
        cap_cat = "Small"
        if mkt_cap > 200000000000: cap_cat = "Large" # > 20k Cr
        elif mkt_cap > 50000000000: cap_cat = "Mid"   # > 5k Cr
        
        metadata = {
            "sector": sector,
            "market_cap_category": cap_cat,
            "market_cap_value": mkt_cap
        }
        
        self.metadata_cache[symbol] = metadata
        self._save_metadata_cache()
        return metadata

    def get_stocks_by_sector(self, sector: str) -> list[str]:
        return [s["symbol"] for s in self.stock_master if s.get("sector") == sector]

    def get_sector_index_symbol(self, sector: str) -> str:
        """Returns the yfinance/TwelveData index symbol for a sector."""
        return self.INDEX_MAP.get(sector, "^NSEI")

    def get_sector_for_symbol(self, symbol: str) -> str:
        """
        Robustly determines the sector for a symbol.
        Cleans suffixes and checks SECTOR_MAP and metadata_cache.
        """
        clean_sym = symbol.split(".")[0].upper()
        
        # 1. Check metadata cache (Phase 52)
        if symbol in self.metadata_cache:
            return self.metadata_cache[symbol].get("sector", "General")
        if clean_sym in self.metadata_cache:
            return self.metadata_cache[clean_sym].get("sector", "General")
            
        # 2. Check static SECTOR_MAP
        if clean_sym in self.SECTOR_MAP:
            return self.SECTOR_MAP[clean_sym]
        
        # 3. Check stock master
        for item in self.stock_master:
            if item["symbol"].split(".")[0].upper() == clean_sym:
                return item.get("sector", "General")
                
        return "General"


    async def get_index_performance(self, sector: str, period: str = "5y") -> pd.DataFrame:
        """
        Fetch historical performance for the sector index.
        Used for relative strength comparison (Phase 30).
        """
        index_symbol = self.get_sector_index_symbol(sector)
        
        # Check Cache
        current_time = time.time()
        cache_key = f"{index_symbol}_{period}"
        if cache_key in self.index_cache:
            entry = self.index_cache[cache_key]
            if current_time - entry["timestamp"] < self.INDEX_CACHE_DURATION:
                return entry["data"]
                
        df = await self.get_ohlc(index_symbol, period=period, interval="1d")
        
        if not df.empty:
            self.index_cache[cache_key] = {"timestamp": current_time, "data": df}
            
        return df


    async def get_live_price(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch live price data using Professional API or Community Fallback.
        Implements Caching (TTL=60s) to prevent Rate Limiting.
        """
        # 0. Check Cache
        current_time = time.time()
        if symbol in self.price_cache:
            entry = self.price_cache[symbol]
            if current_time - entry["timestamp"] < self.CACHE_DURATION:
                return entry["data"]

        # 1. Try TwelveData if configured and not disabled
        if self.td and not self.td_disabled and not symbol.startswith("^"):
            try:
                def _fetch_td():
                    # Strip .NS or .BO for TwelveData
                    clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
                    td_symbol = f"{clean_symbol}:NSE" if ":" not in clean_symbol else clean_symbol
                    res = self.td.price(symbol=td_symbol).as_json()
                    if 'code' in res and res['code'] == 429: # Rate Limit
                         raise ValueError("RATE_LIMIT")
                    if 'price' not in res:
                        raise ValueError(f"Invalid TD Response: {res}")
                    return float(res['price'])
                
                price = await asyncio.wait_for(asyncio.to_thread(_fetch_td), timeout=10.0)
                result = {
                    "symbol": symbol.upper(),
                    "price": round(price, 2),
                    "change": 0.0, 
                    "change_percent": 0.0,
                    "volume": 0,
                    "prev_close": 0.0,
                    "source": "TwelveData (RT)"
                }
                # Update Cache
                self.price_cache[symbol] = {"timestamp": current_time, "data": result}
                return result

            except Exception as e:
                msg = str(e).upper()
                if "CREDITS" in msg:
                    print(f"️ TwelveData Credits Exhausted. Disabling.")
                    self.td_disabled = True
                elif "429" in msg or "RATE_LIMIT" in msg:
                    # TwelveData Credits Exhausted -> Cooldown 15 mins
                    print(f"️ TwelveData Credits Exhausted for {symbol}. Cooling down for 15m.")
                    self.td_disabled = True
                    self.td_disabled_until = time.time() + 900 # 15 mins
                else:
                    err_msg = str(e)
                    # Phase 98: Truncate HTML/Verbose logs
                    err_preview = (err_msg[:100] + "...") if len(err_msg) > 100 else err_msg
                    print(f"TwelveData failed for {symbol}: {err_preview}. Falling back to Yahoo.")
                    
                    # Phase 98: Circuit Breaker for 520/5xx (Server Level issues)
                    if "520" in err_msg or "500" in err_msg or "502" in err_msg:
                        print(f" TwelveData 5xx Error detected. Cooling down for 30m.")
                        self.td_disabled = True
                        self.td_disabled_until = time.time() + 1800 # 30 mins

        # 2. Fallback to Yahoo Finance (Multiple Candidates only if symbolic)
        base_sym = symbol.replace(".NS", "").replace(".BO", "")
        if not symbol.startswith("^") and "." not in symbol:
            candidates = [f"{base_sym}.NS", f"{base_sym}.BO", base_sym]
        else:
            candidates = [symbol]

        last_error = "Unknown"
        for ticker_symbol in candidates:
            try:
                # Use session for Ticker (Phase 97: Timeout Resolution)
                def _fetch_yf():
                    ticker = yf.Ticker(ticker_symbol)
                    
                    try:
                        # 1. Try History first (3s timeout for very latest)
                        hist = ticker.history(period="1d", timeout=5.0)
                        if not hist.empty:
                            p = hist["Close"].iloc[-1]
                            pc = hist["Open"].iloc[0]
                            v = hist["Volume"].iloc[-1]
                            try: mc = ticker.fast_info.market_cap
                            except: mc = 0
                            return {"price": p, "prev_close": pc, "volume": v, "market_cap": mc}
                    except (TypeError, ValueError) as e:
                        # Catch yfinance internal 'NoneType' or logic errors
                        if "subscriptable" in str(e) or "NoneType" in str(e):
                             pass # Fallback to fast_info
                        else: raise e
                    
                    # 2. Fallback to fast_info
                    try:
                        # fast_info can also trigger TypeError in some yfinance versions
                        p = ticker.fast_info.last_price
                        pc = ticker.fast_info.previous_close
                        v = ticker.fast_info.last_volume
                        mc = ticker.fast_info.market_cap
                        return {"price": p, "prev_close": pc, "volume": v, "market_cap": mc}
                    except Exception:
                         raise ValueError("No Data")
                
                yf_data_timeout = 8.0 
                # Wrap with retry
                data = await self._async_retry(
                    lambda: asyncio.wait_for(asyncio.to_thread(_fetch_yf), timeout=yf_data_timeout)
                )
                
                if not data or data.get("price") is None:
                    continue

                price = data.get("price")
                prev_close = data.get("prev_close")
                
                # If we got here, we have a valid price
                change = price - (prev_close if prev_close else price)
                change_percent = (change / prev_close) * 100 if prev_close else 0
                
                result = {
                    "symbol": symbol.upper(),
                    "price": round(float(price), 2),
                    "change": round(float(change), 2),
                    "change_percent": round(float(change_percent), 2),
                    "volume": data.get("volume") or 0,
                    "market_cap": data.get("market_cap") or 0,
                    "prev_close": round(float(prev_close), 2) if prev_close else 0.0,
                    "source": f"Yahoo Finance ({ticker_symbol})"
                }
                # Update Cache
                self.price_cache[symbol] = {"timestamp": current_time, "data": result}
                return result

            except Exception as e:
                err_msg = str(e).upper()
                if "401" in err_msg or "UNAUTHORIZED" in err_msg or "CRUMB" in err_msg:
                    print(f" YF Crumb/Session invalid (Live Price 401) for {ticker_symbol}. Retrying...")
                    last_error = str(e) # Update last_error before continuing
                    continue # Try next candidate

                last_error = str(e)
                # Filter out verbose traceback for known yfinance library bug (NoneType subscriptable)
                if "subscriptable" in last_error or "'NoneType' object" in last_error:
                    print(f"️ Yahoo Finance library bug (NoneType) for {ticker_symbol}. Traceback suppressed.")
                else:
                    print(f"DEBUG: Yahoo Direct failed for {ticker_symbol}: {last_error}")
                
                # If Invalid Crumb or Unauthorized, it's a specific block
                if "401" in last_error or "Crumb" in last_error or "Unauthorized" in last_error:
                    print(f"️ Yahoo Blocked (Crumb/401) for {ticker_symbol}. Triggering Proxy.")

                # Proxy Fallback
                try:
                    res = await self._fetch_live_with_proxy(ticker_symbol)
                    if res:
                         # Cache it too
                         self.price_cache[symbol] = {"timestamp": current_time, "data": res}
                         return res
                except: pass
                
                continue # Try next candidate

        # Final Failover
        print(f"Yahoo Live failed for all candidates of {symbol}: {last_error}")
        
        # Distinguish Rate Limit in Result
        source_msg = f"Error: {last_error}"
        if "rate limit" in last_error.lower() or "too many requests" in last_error.lower():
            source_msg = "Rate Limit (Skipped)"

        return {
            "symbol": symbol.upper(),
            "price": 0.0,
            "change": 0.0,
            "change_percent": 0.0,
            "volume": 0,
            "prev_close": 0.0,
            "source": source_msg
        }

    def _generate_mock_ohlc(self, symbol: str, interval: str = "15m") -> pd.DataFrame:
        # Mock logic removed
        return pd.DataFrame()

    async def get_fundamentals(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch fundamental data (Info dict) using simple yfinance caching.
        """
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^") else symbol
        try:
            def _fetch_info():
                ticker = yf.Ticker(ticker_symbol)
                try:
                    res = ticker.info
                    return res if isinstance(res, dict) else {}
                except Exception:
                    return {}
            
            info = await self._async_retry(
                lambda: asyncio.wait_for(asyncio.to_thread(_fetch_info), timeout=15.0)
            )
            return info if info else {}
        except Exception as e:
            print(f"Fundamental fetch failed for {symbol}: {e}")
            return {}

    async def get_extended_data(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch Holders and News for Sentiment/Risk Analysis.
        """
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^") else symbol
        try:
            def _fetch_ext():
                t = yf.Ticker(ticker_symbol)
                holders = {}
                try:
                    mh = t.major_holders
                    if mh is not None and not mh.empty:
                        if 'Breakdown' in mh.columns:
                            mh.set_index('Breakdown', inplace=True)
                            holders = mh['Value'].to_dict()
                        elif 0 in mh.columns and 1 in mh.columns:
                            holders = dict(zip(mh[1], mh[0]))
                except Exception:
                    pass

                news = []
                try:
                    news = t.news if t.news else []
                except Exception: pass
                
                insider_transactions = []
                try:
                    it = t.insider_transactions
                    if it is not None and not it.empty:
                        it_reset = it.reset_index()
                        insider_transactions = it_reset.to_dict('records')
                except Exception: pass

                return {"holders": holders, "news": news, "insider_transactions": insider_transactions}

            return await self._async_retry(
                lambda: asyncio.wait_for(asyncio.to_thread(_fetch_ext), timeout=20.0)
            )
        except Exception as e:
            print(f"Extended data fetch failed for {symbol}: {e}")
            return {"holders": {}, "news": []}

    async def get_historical_financials(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch historical yearly Income Statement for CAGR calculation.
        """
        current_time = time.time()
        if symbol in self.financials_cache:
            entry = self.financials_cache[symbol]
            if current_time - entry["timestamp"] < self.EXTENDED_CACHE_DURATION: # Re-use 24h
                return entry["data"]

        ticker_symbol = f"{symbol}.NS" if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^") else symbol
        try:
            def _fetch_hist():
                t = yf.Ticker(ticker_symbol)
                return t.financials
            
            df = await self._async_retry(
                lambda: asyncio.wait_for(asyncio.to_thread(_fetch_hist), timeout=30.0)
            ) # Financials can be slow
            self.financials_cache[symbol] = {"timestamp": current_time, "data": df}
            return df
        except Exception as e:
            print(f"Historical financial fetch failed for {symbol}: {e}")
            return pd.DataFrame()


    async def _fetch_hist_with_proxy(self, symbol: str, period: str, interval: str) -> pd.DataFrame:
        """
        Attempts to fetch history using rotating proxies when main connection fails.
        """
        print(f" Switching to Proxy for {symbol}...")
        for _ in range(3): # Try 3 different proxies max
            proxy = await proxy_manager.get_proxy()
            if not proxy: break
            
            try:
                def _try_fetch():
                    ticker = yf.Ticker(symbol, proxy=proxy) 
                    return ticker.history(period=period, interval=interval)
                
                df = await asyncio.wait_for(asyncio.to_thread(_try_fetch), timeout=15.0)
                
                if not df.empty:
                    print(f" Proxy Fetch Success for {symbol} via {proxy}")
                    return df
                else:
                    print(f" Proxy {proxy} returned empty for {symbol}")
                    proxy_manager.blacklist(proxy)
            except Exception as e:
                # print(f"Proxy {proxy} failed for {symbol}: {e}")
                proxy_manager.blacklist(proxy)
        
        return pd.DataFrame()

    async def _fetch_live_with_proxy(self, symbol: str) -> Dict[str, Any]:
        """Fetch live price via proxy."""
        print(f" Switching to Proxy for Live Price {symbol}...")
        for _ in range(2):
            proxy = await proxy_manager.get_proxy()
            if not proxy: break
            try:
                def _try():
                    t = yf.Ticker(symbol, proxy=proxy)
                    # fast_info might be unstable with proxy, use history
                    hist = t.history(period="1d")
                    if hist.empty: raise ValueError("Empty")
                    price = hist['Close'].iloc[-1]
                    return {"price": price, "prev_close": hist['Open'].iloc[0], "volume": hist['Volume'].iloc[-1]}
                
                data = await asyncio.wait_for(asyncio.to_thread(_try), timeout=10.0)
                if data:
                    print(f" Proxy Live Success for {symbol}")
                    # Calculate change if possible
                    p = data['price']
                    pc = data['prev_close']
                    ch = p - pc
                    ch_p = (ch/pc)*100 if pc else 0
                    
                    return {
                        "symbol": symbol.upper(),
                        "price": round(float(p), 2),
                        "change": round(float(ch), 2),
                        "change_percent": round(float(ch_p), 2),
                        "volume": int(data['volume']),
                        "market_cap": 0,
                        "prev_close": round(float(pc), 2),
                        "source": f"Yahoo Proxy"
                    }
            except Exception:
                proxy_manager.blacklist(proxy)
        return {}


    async def get_historical_intraday(self, symbol: str, interval: str = "15m", period: str = "1mo") -> pd.DataFrame:
        """Alias for get_ohlc with intraday defaults."""
        return await self.get_ohlc(symbol, period=period, interval=interval)

    async def get_ohlc(self, symbol: str, period: str = "1mo", interval: str = "1d", fast_fail: bool = False) -> pd.DataFrame:
        """
        Fetch OHLCV data with TwelveData -> Yahoo -> Empty Fallback.
        Implements Caching (TTL=300s) to prevent duplicate API calls.
        """
        # 0. Check Cache
        current_time = time.time()
        cache_key = f"{symbol}_{period}_{interval}"
        if cache_key in self.ohlc_cache:
            entry = self.ohlc_cache[cache_key]
            if current_time - entry["timestamp"] < self.OHLC_CACHE_DURATION:
                return entry["data"]

        # Throttling: Small sleep to prevent rate limits (0.3s - 0.5s)
        await asyncio.sleep(random.uniform(0.3, 0.5))

        # 0. Check TD Cooldown
        if self.td_disabled and time.time() > self.td_disabled_until:
            self.td_disabled = False
            print(" TwelveData Cooldown expired. Re-enabling.")

        # 1. Try TwelveData
        if self.td and not self.td_disabled and not symbol.startswith("^"):
            try:
                td_interval = interval
                if interval == "15m": td_interval = "15min"
                elif interval == "1d": td_interval = "1day"
                elif interval == "1wk": td_interval = "1week"

                def _fetch_td_hist():
                    outputsize = 100
                    if td_interval == "15min": outputsize = 75
                    elif td_interval == "1day": outputsize = 180
                    elif td_interval == "1week": outputsize = 260
                    
                    clean_symbol = symbol.replace(".NS", "").replace(".BO", "")
                    td_symbol = f"{clean_symbol}:NSE" if ":" not in clean_symbol else clean_symbol
                    return self.td.time_series(
                        symbol=td_symbol,
                        interval=td_interval,
                        outputsize=outputsize
                    ).as_pandas()

                df = await asyncio.wait_for(asyncio.to_thread(_fetch_td_hist), timeout=15.0)
                if not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    return df
            except Exception as e:
                msg = str(e).upper()
                if "CREDITS" in msg:
                    print(f"️ TwelveData Credits Exhausted (OHLC). Cooling down for 15m.")
                    self.td_disabled = True
                    self.td_disabled_until = current_time + 900
                elif "429" in msg:
                    print(f" TwelveData Rate Limited (OHLC) for {symbol}. Skipping.")
                else:
                    err_msg = str(e).upper()
                    if "NAMERESOLUTIONERROR" in err_msg or "GETADDRINFO FAILED" in err_msg:
                         print(f" DNS Resolution failed for TwelveData ({symbol}). Likely network issue.")
                    else:
                         err_msg = str(e)
                         err_preview = (err_msg[:100] + "...") if len(err_msg) > 100 else err_msg
                         print(f"TwelveData OHLC failed for {symbol}: {err_preview}")
                         
                         # Phase 98: Circuit Breaker for 520/5xx
                         if "520" in err_msg or "500" in err_msg or "502" in err_msg:
                             print(f" TwelveData 5xx Error detected. Cooling down for 30m.")
                             self.td_disabled = True
                             self.td_disabled_until = time.time() + 1800

        # 2. Fallback to Yahoo Finance (Multiple Candidates only if symbolic)
        base_sym = symbol.replace(".NS", "").replace(".BO", "")
        if not symbol.startswith("^") and "." not in symbol:
            candidates = [f"{base_sym}.NS", f"{base_sym}.BO", base_sym]
        else:
            candidates = [symbol]

        for ticker_symbol in candidates:
            # 1. Prioritize yf.Ticker history 
            try:
                yf_timeout = 8.0 if fast_fail else 15.0
                def _fetch_yf_hist():
                    ticker = yf.Ticker(ticker_symbol)
                    effective_period = "7d" if interval in ["5m", "15m"] else period
                    hist = ticker.history(period=effective_period, interval=interval, timeout=yf_timeout)
                    if not hist.empty:
                        hist.columns = [c.lower() for c in hist.columns]
                    return hist

                df = await self._async_retry(
                    lambda: asyncio.wait_for(asyncio.to_thread(_fetch_yf_hist), timeout=yf_timeout)
                )
                
                if df is not None and not df.empty and len(df) >= (5 if "1d" in interval else 2):
                    # Defensive Validation
                    required = ['open', 'high', 'low', 'close', 'volume']
                    if all(col in df.columns for col in required):
                         # Handle MultiIndex if present
                         if isinstance(df.columns, pd.MultiIndex): 
                             df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
                         
                         # Update Cache
                         self.ohlc_cache[cache_key] = {"timestamp": current_time, "data": df}
                         return df
            except YFRateLimitError:
                print(f" YF Rate Limit (OHLC) for {ticker_symbol}. Skipping candidate.")
                continue
            except Exception as e:
                err_msg = str(e).upper()
                if "401" in err_msg or "UNAUTHORIZED" in err_msg or "CRUMB" in err_msg:
                    print(f" YF Crumb/Session invalid (401) for {ticker_symbol}. Retrying...")
                pass

            # 2. Fallback to yf.download
            try:
                dl_timeout = 12.0 if fast_fail else 20.0
                def _fetch_yf_dl():
                    return yf.download(ticker_symbol, period=period, interval=interval, progress=False, timeout=dl_timeout)
                
                df_dl = await self._async_retry(
                    lambda: asyncio.wait_for(asyncio.to_thread(_fetch_yf_dl), timeout=dl_timeout)
                )
                
                if df_dl is not None and not df_dl.empty and len(df_dl) > 2:
                    if isinstance(df_dl.columns, pd.MultiIndex):
                        df_dl.columns = df_dl.columns.get_level_values(0)
                    df_dl.columns = [c.lower() for c in df_dl.columns]
                    
                    required = ['open', 'high', 'low', 'close', 'volume']
                    if all(col in df_dl.columns for col in required):
                        self.ohlc_cache[cache_key] = {"timestamp": current_time, "data": df_dl}
                        return df_dl
            except YFRateLimitError:
                print(f" YF Rate Limit (Download) for {ticker_symbol}. Skipping candidate.")
                continue
            except Exception as e:
                err_msg = str(e).upper()
                if "401" in err_msg or "UNAUTHORIZED" in err_msg or "CRUMB" in err_msg:
                    print(f" YF Crumb/Session invalid (401 Download) for {ticker_symbol}. Retrying...")
                pass

            if fast_fail:
                print(f" fast_fail enabled for {symbol}, bypassing proxy retry loop.")
                continue

            # Proxy Fallback
            try:
                df_proxy = await self._fetch_hist_with_proxy(ticker_symbol, period, interval)
                if not df_proxy.empty and len(df_proxy) > 2:
                    # ... processing already handles multiindex
                    return df_proxy
            except Exception:
                pass
            
            
            continue # Try next candidate

        # 3. Resampling Fallback (Specific for 15m issues)
        if interval == "15m":
            print(f"️ 15m fetch failed for {symbol}. Attempting 5m resampling...")
            try:
                df_5m = await self.get_ohlc(symbol, period=period, interval="5m")
                if not df_5m.empty:
                    # Resample 5m -> 15m
                    logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
                    df_15m = df_5m.resample('15min').agg(logic).dropna()
                    return df_15m
            except Exception as e:
                print(f"Resampling failed: {e}")

        # 4. Desperate Fallback: yf.download
        if interval in ["15m", "5m"]:
            print(f"️ attempting yf.download fallback for {symbol}...")
            try:
                # IMPORTANT: yf.download returns a MultiIndex columns by default in newer versions
                # when fetching single ticker, we need to handle it.
                # yf.download is slow, 25s timeout
                df = await asyncio.wait_for(asyncio.to_thread(yf.download, tickers=symbol, period=period, interval=interval, progress=False), timeout=25.0)
                
                if not df.empty and len(df) > 2:
                    # Flatten columns if MultiIndex (Price, Ticker) -> Price
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                    
                    df.columns = [c.lower() for c in df.columns]
                    return df
            except Exception as e:
                print(f"yf.download failed: {e}")

        return pd.DataFrame()

    async def get_latest_price(self, symbol: str) -> float:
        """
        Fetch CMP using the robust get_live_price method.
        """
        data = await self.get_live_price(symbol)
        if data and "price" in data:
            return data["price"]
        return 0.0

    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get market status (indices).
        """
        try:
            # Phase 97: Direct cache check to avoid async overhead for status polling
            now = time.time()
            if "^NSEI" in self.price_cache and now - self.price_cache["^NSEI"]["timestamp"] < self.INDEX_CACHE_DURATION:
                nifty = self.price_cache["^NSEI"]["data"]["price"]
                vix = self.price_cache.get("^INDIAVIX", {}).get("data", {}).get("price", 0.0)
                return {
                    "nifty_50": round(nifty, 2),
                    "india_vix": round(vix, 2),
                    "status": "OPEN" if vix > 0 else "CLOSED"
                }

            nifty_task = self.get_latest_price("^NSEI")
            vix_task = self.get_latest_price("^INDIAVIX")
            
            nifty, vix = await asyncio.gather(nifty_task, vix_task)
            
            return {
                "nifty_50": round(nifty, 2),
                "india_vix": round(vix, 2),
                "status": "OPEN" if vix > 0 else "CLOSED"
            }
        except Exception as e:
            print(f"Status check failed: {e}")
            return {"nifty_50": 0.0, "india_vix": 0.0, "status": "UNKNOWN"}

    async def get_advance_decline_ratio(self) -> float:
        """
        Calculates the Advance/Decline ratio using parallelized live price fetches.
        This preserves specialized proxy/error logic while keeping speed.
        """
        try:
            # Take a strategic subset (40 mid/large caps as proxy)
            symbols = [f"{s}.NS" for s in list(self.SECTOR_MAP.keys())[:40]]
            
            # Fetch all in parallel using the proxy-aware get_live_price
            tasks = [self.get_live_price(sym) for sym in symbols]
            results = await asyncio.gather(*tasks)
            
            advances = 0
            declines = 0
            
            for res in results:
                if not res or res.get("price", 0) == 0:
                    continue
                
                p = res.get("price", 0)
                pc = res.get("prev_close", 0)
                
                if p > pc and pc > 0:
                    advances += 1
                elif p < pc and pc > 0:
                    declines += 1
            
            ratio = (advances / declines) if declines > 0 else (advances if advances > 0 else 1.0)
            return round(ratio, 2)
        except Exception as e:
            print(f"A/D check failed: {e}")
            return 1.0

    async def get_sector_performances(self) -> Dict[str, float]:
        """
        Calculates the day change percentage for all sector indices.
        Returns a map of {Sector Name: change_pct}.
        """
        try:
            sector_names = list(self.INDEX_MAP.keys())
            index_symbols = [self.INDEX_MAP[s] for s in sector_names]
            
            # Fetch all in parallel
            tasks = [self.get_live_price(sym) for sym in index_symbols]
            results = await asyncio.gather(*tasks)
            
            sector_perfs = {}
            for i, res in enumerate(results):
                sector = sector_names[i]
                if res and res.get("price", 0) > 0:
                    p = res.get("price")
                    pc = res.get("prev_close")
                    change_pct = ((p - pc) / pc) * 100 if pc > 0 else 0.0
                    sector_perfs[sector] = round(change_pct, 2)
                else:
                    sector_perfs[sector] = 0.0
            
            return sector_perfs
        except Exception as e:
            print(f"Sector performance check failed: {e}")
            return {}

market_service = MarketDataService()
