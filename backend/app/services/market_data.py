import os
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

import yfinance as yf
import pandas as pd
from typing import Dict, Any
import asyncio
from app.core.config import settings
from twelvedata import TDClient

import time

from app.services.market_discovery import market_discovery

class MarketDataService:
    def __init__(self):
        # Cache Config
        self.price_cache = {}
        self.CACHE_DURATION = 60 # seconds

        # Robust Persistence: Session with Retries
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        self.session = requests.Session()
        self.session.trust_env = False # Ignore system proxies
        retries = Retry(
            total=5, 
            backoff_factor=1, 
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Origin': 'https://finance.yahoo.com',
            'Referer': 'https://finance.yahoo.com/'
        })

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

        # Initialize TwelveData client if key is available
        self.td = None
        if settings.MARKET_DATA_API_KEY and "your_twelvedata" not in settings.MARKET_DATA_API_KEY:
            self.td = TDClient(apikey=settings.MARKET_DATA_API_KEY)
            print("MarketDataService: Professional API (TwelveData) Enabled.")
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

        # Circuit Breaker for TwelveData (Permanent Disable if limit hit)
        self.td_disabled = False

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
            data = {"sector": self.SECTOR_MAP[symbol], "market_cap": "Large"} # Default to Large if in static map
            self.metadata_cache[symbol] = data
            return data
            
        print(f"📡 Metadata Fetch for {symbol}...")
        info = await self.get_fundamentals(symbol)
        
        sector = info.get("sector", "Services")
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
        return await self.get_ohlc(index_symbol, period=period, interval="1d")


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
                
                price = await asyncio.to_thread(_fetch_td)
                result = {
                    "symbol": symbol.upper(),
                    "price": round(price, 2),
                    "change": 0.0, 
                    "change_percent": 0.0,
                    "volume": 0,
                    "prev_close": 0.0,
                    "source": "TwelveData (Real-Time)"
                }
                # Update Cache
                self.price_cache[symbol] = {"timestamp": current_time, "data": result}
                return result

            except Exception as e:
                msg = str(e)
                if "credits" in msg or "RATE_LIMIT" in msg or "429" in msg:
                    print(f"⚠️ TwelveData Rate Limit/Credits exhausted. Disabling TwelveData for this session.")
                    self.td_disabled = True
                print(f"TwelveData failed for {symbol}: {e}. Falling back to Yahoo.")

        # 2. Fallback to Yahoo Finance (Multiple Candidates)
        candidates = []
        if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^"):
            candidates = [f"{symbol}.NS", f"{symbol}.BO", symbol]
        else:
            candidates = [symbol]

        last_error = "Unknown"
        for ticker_symbol in candidates:
            try:
                def _fetch_yf():
                    ticker = yf.Ticker(ticker_symbol)
                    # fast_info can return NaN or None
                    p = ticker.fast_info.last_price
                    pc = ticker.fast_info.previous_close
                    v = ticker.fast_info.last_volume
                    mc = ticker.fast_info.market_cap
                    
                    if p is None or (isinstance(p, float) and np.isnan(p)) or p <= 0:
                         raise ValueError("Invalid Price")
                    return {"price": p, "prev_close": pc, "volume": v, "market_cap": mc}
                
                import numpy as np
                data = await asyncio.to_thread(_fetch_yf)
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
                last_error = str(e)
                continue # Try next candidate

        # Final Failover
        print(f"Yahoo Live failed for all candidates of {symbol}: {last_error}")
        return {
            "symbol": symbol.upper(),
            "price": 0.0,
            "change": 0.0,
            "change_percent": 0.0,
            "volume": 0,
            "prev_close": 0.0,
            "source": f"Error: {last_error}"
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
                return ticker.info
            
            info = await asyncio.wait_for(asyncio.to_thread(_fetch_info), timeout=15.0)
            return info
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

                news = t.news if t.news else []
                
                insider_transactions = []
                try:
                    it = t.insider_transactions
                    if it is not None and not it.empty:
                        it_reset = it.reset_index()
                        insider_transactions = it_reset.to_dict('records')
                except Exception: pass

                return {"holders": holders, "news": news, "insider_transactions": insider_transactions}

            return await asyncio.wait_for(asyncio.to_thread(_fetch_ext), timeout=15.0)
        except Exception as e:
            print(f"Extended data fetch failed for {symbol}: {e}")
            return {"holders": {}, "news": []}

    async def get_historical_financials(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch historical yearly Income Statement for CAGR calculation.
        """
        ticker_symbol = f"{symbol}.NS" if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^") else symbol
        try:
            def _fetch_hist():
                t = yf.Ticker(ticker_symbol)
                return t.financials
            
            df = await asyncio.wait_for(asyncio.to_thread(_fetch_hist), timeout=20.0) # Financials can be slow
            return df
        except Exception as e:
            print(f"Historical financial fetch failed for {symbol}: {e}")
            return pd.DataFrame()

    async def get_ohlc(self, symbol: str, period: str = "1mo", interval: str = "1d") -> pd.DataFrame:
        """
        Fetch OHLCV data with TwelveData -> Yahoo -> Empty Fallback.
        """
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

                df = await asyncio.to_thread(_fetch_td_hist)
                if not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    return df
            except Exception as e:
                msg = str(e)
                if "credits" in msg or "429" in msg:
                    print(f"⚠️ TwelveData Credits Exhausted (OHLC). Disabling TwelveData.")
                    self.td_disabled = True
                print(f"TwelveData OHLC failed for {symbol}: {e}")

        # 2. Fallback to Yahoo Finance (Multiple Candidates)
        candidates = []
        if not symbol.endswith((".NS", ".BO")) and not symbol.startswith("^"):
            candidates = [f"{symbol}.NS", f"{symbol}.BO", symbol]
        else:
            candidates = [symbol]

        for ticker_symbol in candidates:
            try:
                def _fetch_yf_hist():
                    ticker = yf.Ticker(ticker_symbol)
                    hist = ticker.history(period=period, interval=interval)
                    if not hist.empty:
                        hist.columns = [c.lower() for c in hist.columns]
                    return hist

                df = await asyncio.wait_for(asyncio.to_thread(_fetch_yf_hist), timeout=15.0)
                
                if not df.empty and len(df) >= (5 if "1d" in interval else 2): # Basic sanity check
                    df.columns = [c.lower() for c in df.columns]
                    if isinstance(df.columns, pd.MultiIndex): 
                        df.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df.columns]
                    return df
            except Exception:
                continue # Try next candidate

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

market_service = MarketDataService()
