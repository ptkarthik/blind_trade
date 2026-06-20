"""
[KITE CONNECT] Institutional-Grade Market Data Provider
=======================================================
Replaces Yahoo Finance REST polling with Zerodha Kite Connect for:
- Historical OHLCV candles (15m, 1h, 1d)
- Bulk LTP (Last Traded Price) quotes
- Instrument token mapping (symbol → numeric token)

Architecture:
- OAuth login flow via local callback server
- Session persistence (kite_session.json) — valid ~6-8 hours
- Auto-fallback to Yahoo Fast if Kite session is expired
"""

import os
import json
import time
import asyncio
import logging
import hashlib
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from threading import Thread

logger = logging.getLogger("kite_data")

def _safe_print(msg: str):
    """Print that won't crash on Windows cp1252 console with emojis."""
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode('ascii', 'replace').decode('ascii'))


class KiteDataService:
    """Kite Connect data provider with OAuth session management."""

    def __init__(self):
        self._data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self._session_file = os.path.join(self._data_dir, "kite_session.json")
        self._instruments_file = os.path.join(self._data_dir, "kite_instruments.json")

        self._kite = None          # KiteConnect instance
        self._access_token = None
        self._instruments = {}     # {symbol_str: instrument_token_int}
        self._is_ready = False
        self._callback_server = None

        self._hist_semaphore = None
        self._quote_semaphore = None
        self._quote_lock = None

    def _ensure_locks(self):
        if self._hist_semaphore is None:
            self._hist_semaphore = asyncio.Semaphore(1)  # Fully serialize to prevent requests.Session thread deadlocks
            self._quote_semaphore = asyncio.Semaphore(1)  # Fully serialize
            self._quote_lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        if not self._is_ready or not self._access_token:
            return False
            
        # Hard check expiration of the token to prevent false "Connected" UI states
        if not os.path.exists(self._session_file):
            return False
        try:
            import json
            from datetime import datetime
            with open(self._session_file, "r") as f:
                session = json.load(f)
            login_time = datetime.fromisoformat(session["login_time"])
            age_hours = (datetime.now() - login_time).total_seconds() / 3600
            if age_hours > 8:
                return False
        except Exception:
            return False
            
        return True

    # =========================================================================
    # INITIALIZATION & AUTH
    # =========================================================================

    async def initialize(self):
        """Bootstrap Kite Connect — load saved session or prompt login."""
        from app.core.config import settings

        api_key = settings.KITE_API_KEY
        api_secret = settings.KITE_API_SECRET

        if not api_key or not api_secret:
            print("️ [KITE] No API key/secret in .env — Kite disabled, using Yahoo fallback")
            return

        try:
            from kiteconnect import KiteConnect
            self._kite = KiteConnect(api_key=api_key, timeout=10)
        except ImportError:
            print(" [KITE] kiteconnect package not installed. Run: pip install kiteconnect")
            return

        print("Testing _load_session")
        # Try loading existing session
        if await self._load_session():
            print(" [KITE] Restored session from cache")
            print("Testing _load_instruments")
            await self._load_instruments()
            self._is_ready = True
            print("Kite ready")
            return

        print("Testing _auto_login")
        # Try automated login (no browser needed)
        if await self._auto_login():
            print(" [KITE] Auto-login successful!")
            await self._load_instruments()
            self._is_ready = True
            return

        # Fallback: manual browser login
        login_url = self._kite.login_url()
        print(f"[KITE] Auto-login failed. Open this URL manually: {login_url}")
        self._start_callback_server()

    async def _auto_login(self) -> bool:
        """Fully automated Kite login using Selenium headless Edge (no browser required for the user)."""
        from app.core.config import settings

        user_id = settings.KITE_USER_ID
        password = settings.KITE_PASSWORD
        totp_secret = settings.KITE_TOTP_SECRET
        api_key = settings.KITE_API_KEY
        api_secret = settings.KITE_API_SECRET

        if not all([user_id, password, totp_secret, api_key, api_secret]):
            logger.info("️ [KITE] Auto-login skipped — missing KITE_USER_ID/PASSWORD/TOTP_SECRET in .env")
            return False

        try:
            logger.info(" [KITE] Attempting automated login via headless browser...")
            import asyncio
            result = await asyncio.to_thread(
                self._run_selenium_login,
                user_id, password, totp_secret, api_key, api_secret
            )
            return result
        except Exception as e:
            logger.error(f"[KITE] Auto-login failed: {e}")
            import traceback
            err_str = traceback.format_exc()
            try:
                with open(os.path.join(self._data_dir, "kite_login_error.txt"), "w") as f:
                    f.write(f"Error: {e}\n\nTraceback:\n{err_str}")
            except:
                pass
            return False

    def _run_selenium_login(self, user_id, password, totp_secret, api_key, api_secret) -> bool:
        """Synchronous selenium login logic running in a background thread."""
        import time
        import pyotp
        import urllib.parse
        from selenium import webdriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.chrome.options import Options

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1280,720")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        driver = webdriver.Chrome(options=options)
        wait = WebDriverWait(driver, 15)

        try:
            login_url = f"https://kite.zerodha.com/connect/login?api_key={api_key}&v=3"
            driver.get(login_url)
            time.sleep(2)

            # Enter credentials
            user_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']")))
            user_field.send_keys(user_id)
            pass_field = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pass_field.send_keys(password)
            driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            time.sleep(3)

            # Enter TOTP
            totp = pyotp.TOTP(totp_secret)
            code = totp.now()
            totp_field = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text'], input[type='number'], input[autocomplete='one-time-code']")))
            totp_field.send_keys(code)
            time.sleep(1)
            
            try:
                driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
            except:
                pass
            time.sleep(5)

            # Handle Authorize page if it appears
            current_url = driver.current_url
            if "authorize" in current_url:
                try:
                    auth_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit'], .button-blue, button.btn")))
                    auth_btn.click()
                    time.sleep(3)
                except:
                    buttons = driver.find_elements(By.TAG_NAME, "button")
                    for btn in buttons:
                        if "authorize" in btn.text.lower() or "approve" in btn.text.lower() or "continue" in btn.text.lower():
                            btn.click()
                            time.sleep(3)
                            break
            
            final_url = driver.current_url
            if "request_token=" in final_url:
                parsed = urllib.parse.urlparse(final_url)
                params = urllib.parse.parse_qs(parsed.query)
                request_token = params.get("request_token", [None])[0]
                
                # Exchange request_token for access_token
                data = self._kite.generate_session(request_token, api_secret=api_secret)
                self._access_token = data["access_token"]
                self._kite.set_access_token(self._access_token)

                # Save session
                os.makedirs(self._data_dir, exist_ok=True)
                with open(self._session_file, "w") as f:
                    json.dump({
                        "access_token": self._access_token,
                        "login_time": datetime.now().isoformat(),
                        "user_id": data.get("user_id", user_id)
                    }, f)

                logger.info(f" [KITE] Auto-login successful! User: {data.get('user_id', user_id)}")
                return True
            else:
                logger.error(f"[KITE] Auto-login failed: Did not find request_token in URL {final_url[:100]}")
                return False

        finally:
            driver.quit()

    def _start_callback_server(self):
        """Starts a tiny HTTP server to catch the OAuth redirect callback."""
        from http.server import HTTPServer, BaseHTTPRequestHandler
        import urllib.parse

        parent = self  # Capture reference for the handler

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                params = urllib.parse.parse_qs(parsed.query)

                if "request_token" in params:
                    request_token = params["request_token"][0]
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()

                    # Process the token
                    success = parent._process_login(request_token)

                    if success:
                        self.wfile.write(b"""
                        <html><body style="font-family:Inter,sans-serif;text-align:center;padding:60px;background:#0a0a0a;color:#00ff88">
                        <h1>&#10003; Kite Login Successful!</h1>
                        <p>You can close this tab. The trading engine is now connected to Zerodha.</p>
                        </body></html>
                        """)
                    else:
                        self.wfile.write(b"""
                        <html><body style="font-family:Inter,sans-serif;text-align:center;padding:60px;background:#0a0a0a;color:#ff4444">
                        <h1>&#10007; Login Failed</h1>
                        <p>Check the engine console for errors.</p>
                        </body></html>
                        """)
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Missing request_token")

            def log_message(self, format, *args):
                pass  # Suppress HTTP server logs

        def run_server():
            try:
                server = HTTPServer(("127.0.0.1", 5000), CallbackHandler)
                server.timeout = 300  # 5 min timeout for login
                logger.info(" [KITE] Callback server listening on http://127.0.0.1:5000/callback")
                server.handle_request()  # Handle single request then stop
                server.server_close()
            except OSError as e:
                if "address already in use" in str(e).lower() or "10048" in str(e):
                    logger.warning("️ [KITE] Port 5000 busy — callback server skipped")
                else:
                    logger.error(f" [KITE] Callback server error: {e}")

        thread = Thread(target=run_server, daemon=True)
        thread.start()

    def _process_login(self, request_token: str) -> bool:
        """Exchanges request_token for access_token and persists session."""
        from app.core.config import settings
        try:
            data = self._kite.generate_session(request_token, api_secret=settings.KITE_API_SECRET)
            self._access_token = data["access_token"]
            self._kite.set_access_token(self._access_token)

            # Save session
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._session_file, "w") as f:
                json.dump({
                    "access_token": self._access_token,
                    "login_time": datetime.now().isoformat(),
                    "user_id": data.get("user_id", "")
                }, f)

            logger.info(f" [KITE] Login successful! User: {data.get('user_id', 'unknown')}")

            # Load instruments synchronously (we're in a thread)
            self._load_instruments_sync()
            self._is_ready = True
            return True

        except Exception as e:
            logger.error(f" [KITE] Login failed: {e}")
            return False

    async def _load_session(self) -> bool:
        """Loads and validates a saved session."""
        if not os.path.exists(self._session_file):
            return False

        try:
            with open(self._session_file, "r") as f:
                session = json.load(f)

            login_time = datetime.fromisoformat(session["login_time"])
            age_hours = (datetime.now() - login_time).total_seconds() / 3600

            # Kite sessions are valid for ~6-8 hours (one trading day)
            if age_hours > 8:
                logger.info(" [KITE] Session expired (>8h old)")
                return False

            self._access_token = session["access_token"]
            self._kite.set_access_token(self._access_token)

            # Validate by making a simple API call
            try:
                profile = await asyncio.to_thread(self._kite.profile)
                logger.info(f" [KITE] Session valid — User: {profile.get('user_id', 'unknown')}")
                return True
            except Exception as e:
                logger.warning(f"️ [KITE] Saved session invalid: {e}")
                return False

        except Exception as e:
            logger.warning(f"️ [KITE] Session file corrupt: {e}")
            return False

    # =========================================================================
    # INSTRUMENT TOKEN MAPPING
    # =========================================================================

    def _load_instruments_sync(self):
        """Synchronous instrument loading (called from callback thread)."""
        try:
            # Check cache first
            if os.path.exists(self._instruments_file):
                mtime = os.path.getmtime(self._instruments_file)
                if (time.time() - mtime) < 86400:  # 24h cache
                    with open(self._instruments_file, "r") as f:
                        self._instruments = json.load(f)
                    logger.info(f" [KITE] Loaded {len(self._instruments)} instruments from cache")
                    return

            # Fetch fresh from Kite
            instruments = self._kite.instruments("NSE")
            mapping = {}
            for inst in instruments:
                if inst.get("segment") == "NSE" and inst.get("instrument_type") == "EQ":
                    symbol = inst["tradingsymbol"]
                    mapping[symbol] = inst["instrument_token"]

            self._instruments = mapping

            # Cache
            os.makedirs(self._data_dir, exist_ok=True)
            with open(self._instruments_file, "w") as f:
                json.dump(mapping, f)

            logger.info(f" [KITE] Downloaded {len(mapping)} NSE instrument tokens")

        except Exception as e:
            logger.error(f" [KITE] Instrument fetch failed: {e}")

    async def _load_instruments(self):
        """Async wrapper for instrument loading."""
        await asyncio.to_thread(self._load_instruments_sync)

    def get_token(self, symbol: str) -> Optional[int]:
        """Converts 'RELIANCE.NS' or 'RELIANCE' to instrument_token."""
        clean = symbol.replace(".NS", "").replace(".BO", "").upper()
        # Kite uses exact NSE tradingsymbols (M&M stays M&M, BAJAJ-AUTO stays BAJAJ-AUTO)
        # No cleaning needed — instruments dict has exact NSE symbols
        return self._instruments.get(clean)

    # =========================================================================
    # HISTORICAL DATA (Replaces yahoo_fast.fetch_ohlc)
    # =========================================================================

    async def fetch_ohlc(self, symbol: str, period: str = "7d",
                         interval: str = "15m") -> pd.DataFrame:
        """Fetches historical OHLCV data from Kite Connect.

        Returns DataFrame with same format as yahoo_fast (columns: open, high, low, close, volume).
        Falls back to Yahoo if Kite fails.
        """
        if not self.is_ready:
            return pd.DataFrame()

        token = self.get_token(symbol)
        if token is None:
            return pd.DataFrame()  # Unknown symbol — caller should fallback to Yahoo

        period_days = {"1d": 1, "2d": 2, "5d": 5, "7d": 7, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
        days = period_days.get(period, 7)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        # Map interval strings to Kite format
        interval_map = {
            "1m": "minute", "5m": "5minute", "10m": "10minute",
            "15m": "15minute", "30m": "30minute", "60m": "60minute",
            "1h": "60minute", "1d": "day", "1wk": "week"
        }
        kite_interval = interval_map.get(interval, "15minute")

        self._ensure_locks()
        async with self._hist_semaphore:
            try:
                records = await asyncio.to_thread(
                    self._kite.historical_data,
                    token,
                    from_date.strftime("%Y-%m-%d"),
                    to_date.strftime("%Y-%m-%d"),
                    kite_interval
                )

                if not records:
                    return pd.DataFrame()

                df = pd.DataFrame(records)
                # Kite returns 'date' column — convert to DatetimeIndex
                df.index = pd.to_datetime(df["date"])
                df = df[["open", "high", "low", "close", "volume"]]
                df = df.dropna()
                return df

            except Exception as e:
                # Token expired or rate limited
                if "TokenException" in type(e).__name__ or "403" in str(e):
                    logger.warning(f" [KITE] Session expired during fetch — marking as not ready")
                    self._is_ready = False
                else:
                    logger.debug(f"[KITE] Historical fetch failed for {symbol}: {e}")
                return pd.DataFrame()

    async def fetch_batch(self, symbols: List[str], interval: str = "15m",
                          period: str = "7d", concurrency: int = 5) -> Dict[str, pd.DataFrame]:
        """Fetches batch historical data from Kite with rate limiting.

        Returns same format as yahoo_fast.fetch_batch().
        """
        if not self.is_ready:
            return {}

        results = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def _worker(sym):
            async with semaphore:
                # Small jitter to spread requests
                await asyncio.sleep(0.1)
                df = await self.fetch_ohlc(sym, period=period, interval=interval)
                if not df.empty:
                    results[sym] = df

        await asyncio.gather(*[_worker(s) for s in symbols])
        return results

    # =========================================================================
    # LIVE QUOTES (Replaces market_data.get_batch_prices)
    # =========================================================================

    async def get_ltp(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches Last Traded Price for multiple symbols in one call.

        Returns: {symbol: {"price": float, "change_percent": float, ...}}
        """
        if not self.is_ready or not symbols:
            return {}

        # Build token list
        token_to_sym = {}
        nse_tokens = []
        for sym in symbols:
            token = self.get_token(sym)
            if token:
                key = f"NSE:{sym.replace('.NS', '').upper()}"
                token_to_sym[key] = sym
                nse_tokens.append(key)

        if not nse_tokens:
            return {}

        try:
            # Kite quote API accepts up to 500 instruments per call
            all_quotes = {}
            for i in range(0, len(nse_tokens), 500):
                batch = nse_tokens[i:i+500]
                self._ensure_locks()
                async with self._quote_lock:
                    quotes = await asyncio.to_thread(self._kite.quote, batch)
                all_quotes.update(quotes)

            result = {}
            for key, data in all_quotes.items():
                sym = token_to_sym.get(key)
                if sym:
                    ohlc = data.get("ohlc", {})
                    last_price = data.get("last_price", 0)
                    prev_close = ohlc.get("close", last_price)
                    change_pct = ((last_price - prev_close) / prev_close * 100) if prev_close > 0 else 0

                    result[sym] = {
                        "price": last_price,
                        "change_percent": round(change_pct, 2),
                        "volume": data.get("volume", 0),
                        "source": "Kite"
                    }
                    
            if result:
                logger.info(f" [KITE DATA] Live Prices (LTP) successfully fetched for {len(result)} symbols")

            return result

        except Exception as e:
            if "TokenException" in type(e).__name__:
                self._is_ready = False
                logger.warning(" [KITE] Session expired during quote fetch")
            else:
                logger.error(f" [KITE] Quote fetch failed: {e}")
            return {}

    async def get_live_ohlcv(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetches Live Intraday OHLCV for the current trading day.
        
        Returns: {symbol: {"open": float, "high": float, "low": float, "close": float, "volume": int}}
        Note: 'close' represents the last traded price for the current day.
        """
        if not self.is_ready or not symbols:
            return {}

        token_to_sym = {}
        nse_tokens = []
        for sym in symbols:
            token = self.get_token(sym)
            if token:
                key = f"NSE:{sym.replace('.NS', '').upper()}"
                token_to_sym[key] = sym
                nse_tokens.append(key)

        if not nse_tokens:
            return {}

        try:
            all_quotes = {}
            for i in range(0, len(nse_tokens), 500):
                batch = nse_tokens[i:i+500]
                self._ensure_locks()
                async with self._quote_lock:
                    quotes = await asyncio.to_thread(self._kite.quote, batch)
                all_quotes.update(quotes)

            result = {}
            for key, data in all_quotes.items():
                sym = token_to_sym.get(key)
                if sym:
                    ohlc = data.get("ohlc", {})
                    last_price = data.get("last_price", 0)
                    volume = data.get("volume", 0)
                    
                    if last_price > 0 and ohlc.get("open", 0) > 0:
                        result[sym] = {
                            "open": ohlc.get("open"),
                            "high": max(ohlc.get("high", last_price), last_price),
                            "low": min(ohlc.get("low", last_price), last_price) if ohlc.get("low", 0) > 0 else last_price,
                            "close": last_price,
                            "volume": volume
                        }
            return result
        except Exception as e:
            logger.error(f" [KITE] Live OHLCV fetch failed: {e}")
            return {}

    async def get_market_depth(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """[AUDIT GAP-C] Fetches Level-2 market depth (bid/ask order flow) from Kite.
        
        Returns: {symbol: {
            "buy_quantity": int,      # Total bid volume across 5 levels
            "sell_quantity": int,     # Total ask volume across 5 levels
            "bid_ask_ratio": float,  # buy_qty / sell_qty — >2.0 = institutional buying
            "spread_pct": float,     # (best_ask - best_bid) / mid_price × 100
            "depth_imbalance": str,  # "STRONG_BUY" | "BUY" | "NEUTRAL" | "SELL" | "STRONG_SELL"
        }}
        
        This replaces the CVD proxy (close-position-in-range) with REAL order book data.
        When Kite is not connected, returns empty dict (caller falls back to CVD proxy).
        """
        if not self.is_ready or not symbols:
            return {}

        # Build token list (same as get_ltp)
        token_to_sym = {}
        nse_tokens = []
        for sym in symbols:
            token = self.get_token(sym)
            if token:
                key = f"NSE:{sym.replace('.NS', '').upper()}"
                token_to_sym[key] = sym
                nse_tokens.append(key)

        if not nse_tokens:
            return {}

        try:
            all_quotes = {}
            for i in range(0, len(nse_tokens), 500):
                batch = nse_tokens[i:i+500]
                self._ensure_locks()
                async with self._quote_lock:
                    quotes = await asyncio.to_thread(self._kite.quote, batch)
                all_quotes.update(quotes)

            result = {}
            for key, data in all_quotes.items():
                sym = token_to_sym.get(key)
                if sym:
                    buy_qty = data.get("buy_quantity", 0)
                    sell_qty = data.get("sell_quantity", 0)
                    depth = data.get("depth", {})
                    
                    # Calculate bid-ask spread from top of book
                    spread_pct = 0.0
                    best_bid = 0.0
                    best_ask = 0.0
                    buy_depth = depth.get("buy", [])
                    sell_depth = depth.get("sell", [])
                    
                    if buy_depth and sell_depth:
                        best_bid = buy_depth[0].get("price", 0)
                        best_ask = sell_depth[0].get("price", 0)
                        if best_bid > 0 and best_ask > 0:
                            mid_price = (best_bid + best_ask) / 2
                            spread_pct = ((best_ask - best_bid) / mid_price) * 100
                    
                    # Bid/Ask ratio: institutional flow signal
                    ratio = buy_qty / max(sell_qty, 1)
                    
                    # Classify imbalance
                    if ratio >= 3.0:
                        imbalance = "STRONG_BUY"
                    elif ratio >= 2.0:
                        imbalance = "BUY"
                    elif ratio <= 0.33:
                        imbalance = "STRONG_SELL"
                    elif ratio <= 0.5:
                        imbalance = "SELL"
                    else:
                        imbalance = "NEUTRAL"
                    
                    result[sym] = {
                        "buy_quantity": buy_qty,
                        "sell_quantity": sell_qty,
                        "bid_ask_ratio": round(ratio, 2),
                        "spread_pct": round(spread_pct, 4),
                        "depth_imbalance": imbalance,
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                    }

            if result:
                logger.info(f" [KITE DATA] Level-2 Market Depth successfully fetched for {len(result)} symbols")

            return result

        except Exception as e:
            if "TokenException" in type(e).__name__:
                self._is_ready = False
            logger.debug(f"[KITE] Market depth fetch failed: {e}")
            return {}

    async def get_index_ohlc(self, index_symbol: str = "NIFTY 50",
                              period: str = "7d", interval: str = "15m") -> pd.DataFrame:
        """Fetches index (Nifty/BankNifty) historical data.

        Kite uses special tokens for indices — they are in the instruments list under NSE segment.
        """
        if not self.is_ready:
            return pd.DataFrame()

        # Index tokens (these are standard Kite tokens for indices)
        index_map = {
            "NIFTY 50": 256265,
            "NIFTY BANK": 260105,
            "INDIA VIX": 264969
        }

        token = index_map.get(index_symbol)
        if not token:
            return pd.DataFrame()

        period_days = {"1d": 1, "2d": 2, "5d": 5, "7d": 7, "1mo": 30, "6mo": 180, "1y": 365, "2y": 730}
        days = period_days.get(period, 7)
        to_date = datetime.now()
        from_date = to_date - timedelta(days=days)

        interval_map = {"15m": "15minute", "1h": "60minute", "1d": "day", "5m": "5minute"}
        kite_interval = interval_map.get(interval, "15minute")

        try:
            records = await asyncio.to_thread(
                self._kite.historical_data,
                token,
                from_date.strftime("%Y-%m-%d"),
                to_date.strftime("%Y-%m-%d"),
                kite_interval
            )

            if not records:
                return pd.DataFrame()

            df = pd.DataFrame(records)
            df.index = pd.to_datetime(df["date"])
            df = df[["open", "high", "low", "close", "volume"]]
            return df.dropna()

        except Exception as e:
            logger.error(f" [KITE] Index OHLC failed for {index_symbol}: {e}")
            return pd.DataFrame()

    # =========================================================================
    # STATUS
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Returns current Kite connection status for UI/debugging."""
        session_info = {}
        if os.path.exists(self._session_file):
            try:
                with open(self._session_file, "r") as f:
                    session_info = json.load(f)
            except:
                pass

        return {
            "is_ready": self.is_ready,
            "has_session": self._access_token is not None,
            "instruments_loaded": len(self._instruments),
            "login_time": session_info.get("login_time"),
            "user_id": session_info.get("user_id"),
            "login_url": self._kite.login_url() if self._kite and not self.is_ready else None
        }

    # =========================================================================
    # LIVE EXECUTION MODE
    # =========================================================================

    async def get_margins(self) -> Dict[str, Any]:
        """Fetches live funding margins from Kite."""
        if not self.is_ready:
            return {"error": "Kite not connected"}
        
        try:
            margins = await asyncio.to_thread(self._kite.margins)
            equity_margins = margins.get("equity", {})
            return {
                "available": equity_margins.get("available", {}).get("live_balance", 0.0),
                "used": equity_margins.get("utilised", {}).get("debits", 0.0),
                "opening": equity_margins.get("available", {}).get("opening_balance", 0.0)
            }
        except Exception as e:
            logger.error(f" [KITE] Fetch margins failed: {e}")
            return {"error": str(e)}

    async def place_order(self, symbol: str, quantity: int, transaction_type: str, order_type: str = "MARKET", price: float = 0.0, product_type: str = "CNC") -> Dict[str, Any]:
        """
        Places a live order via Kite API.
        transaction_type: 'BUY' or 'SELL'
        order_type: 'MARKET' or 'LIMIT'
        product_type: 'CNC' or 'MIS'
        """
        if not self.is_ready:
            return {"success": False, "error": "Kite not connected"}

        clean_symbol = symbol.replace(".NS", "").upper()
        
        try:
            from kiteconnect import KiteConnect
            t_type = self._kite.TRANSACTION_TYPE_BUY if transaction_type.upper() == "BUY" else self._kite.TRANSACTION_TYPE_SELL
            o_type = self._kite.ORDER_TYPE_MARKET if order_type.upper() == "MARKET" else self._kite.ORDER_TYPE_LIMIT
            
            product = self._kite.PRODUCT_CNC if product_type.upper() == "CNC" else self._kite.PRODUCT_MIS

            order_args = {
                "tradingsymbol": clean_symbol,
                "exchange": self._kite.EXCHANGE_NSE,
                "transaction_type": t_type,
                "quantity": int(quantity),
                "order_type": o_type,
                "product": product,
                "validity": self._kite.VALIDITY_DAY
            }
            if o_type == self._kite.ORDER_TYPE_LIMIT:
                order_args["price"] = price

            logger.warning(f" [KITE EXECUTION] Placing real {transaction_type} order for {quantity} {clean_symbol}...")
            order_id = await asyncio.to_thread(
                self._kite.place_order,
                variety=self._kite.VARIETY_REGULAR,
                **order_args
            )
            
            logger.info(f" [KITE EXECUTION] Order successful. ID: {order_id}")
            return {"success": True, "order_id": order_id, "message": "Order placed successfully"}
            
        except Exception as e:
            logger.error(f" [KITE EXECUTION] Order failed: {e}")
            return {"success": False, "error": str(e)}


# Singleton
kite_data = KiteDataService()
