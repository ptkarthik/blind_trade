
import asyncio
import requests
import random
import time
import urllib3
import os
import json
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

# Suppress InsecureRequestWarning for proxy validation
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class ProxyManager:
    """
    Manages a pool of free, public proxies to mitigate rate limits.
    Scrapes from reliable GitHub repositories and validates them against Yahoo Finance.
    Uses requests + ThreadPoolExecutor for broad compatibility.
    """
    
    def __init__(self):
        self.proxies: List[str] = []
        self.blacklist_set = set()
        self.last_refresh = 0
        self.REFRESH_INTERVAL = 1800 # 30 minutes
        self.lock = asyncio.Lock()
        
        # Public Proxy Sources (HTTP/HTTPS)
        self.sources = [
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all"
        ]
        
        self.cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "proxy_cache.json")
        self._load_cache()

    def _load_cache(self):
        """Loads proxies from a local cache file."""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cached = json.load(f)
                    if isinstance(cached, list) and cached:
                        self.proxies = cached
                        print(f"[CACHE] ProxyManager: Loaded {len(self.proxies)} proxies from local cache.")
            except Exception as e:
                print(f"[ERROR] Failed to load proxy cache: {e}")

    def _save_cache(self):
        """Saves current valid proxies to a local cache file."""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.proxies, f)
        except Exception as e:
            print(f"[ERROR] Failed to save proxy cache: {e}")

    async def get_proxy(self) -> Optional[str]:
        """
        Returns a valid proxy from the pool.
        Non-blocking: Trigger refresh in background if empty.
        """
        async with self.lock:
            # Phase 94: Non-blocking refresh. If empty or stale, trigger background refresh but return immediately.
            if not self.proxies or (time.time() - self.last_refresh > self.REFRESH_INTERVAL):
                if not getattr(self, "_refreshing", False):
                    self._refreshing = True
                    # Start refresh in background task
                    asyncio.create_task(self._safe_refresh())
            
            if not self.proxies:
                return None
                
            return random.choice(self.proxies)

    async def _safe_refresh(self):
        """Wrapper to ensure _refreshing is reset even on failure."""
        try:
            await self._refresh_proxies()
        finally:
            self._refreshing = False

    def blacklist(self, proxy: str):
        """
        Marks a proxy as bad so it won't be reused immediately.
        """
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self.blacklist_set.add(proxy)
            # print(f"🚫 Proxy Blacklisted: {proxy}")

    async def _refresh_proxies(self):
        """
        Scrapes and Validates new proxies.
        """
        print("[REFRESH] ProxyManager: Refreshing Proxy List (Threaded)...")
        raw_proxies = set()
        
        def fetch_source(url):
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    return resp.text.splitlines()
            except:
                return []
            return []

        # 1. Scrape (Run in thread pool)
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=3) as executor:
            tasks = [loop.run_in_executor(executor, fetch_source, s) for s in self.sources]
            results = await asyncio.gather(*tasks)
            
            for lines in results:
                if lines:
                    for line in lines:
                        if ":" in line and not line.startswith("#"):
                            raw_proxies.add(f"http://{line.strip()}")

        print(f"[STATUS] Found {len(raw_proxies)} raw proxies. Validating...")
        
        # 2. Validate (Batch processing)
        candidates = list(raw_proxies - self.blacklist_set)
        random.shuffle(candidates)
        candidates = candidates[:300] 
        
        valid_proxies = []
        
        def validate_sync(proxy):
            # Reduced timeout for fast check
            target_url = "https://www.google.com" 
            try:
                resp = requests.get(target_url, proxies={"http": proxy, "https": proxy}, timeout=4, verify=False)
                if resp.status_code == 200:
                    return proxy
            except:
                pass
            return None

        # Run validation in thread pool
        with ThreadPoolExecutor(max_workers=50) as executor:
            tasks = [loop.run_in_executor(executor, validate_sync, p) for p in candidates]
            results = await asyncio.gather(*tasks)
            
        valid_proxies = [p for p in results if p]
        
        if valid_proxies:
            self.proxies = valid_proxies
            self.last_refresh = time.time()
            self.blacklist_set.clear() # Reset blacklist on new fetch
            self._save_cache()
            print(f"[SUCCESS] ProxyManager: Activated {len(self.proxies)} working proxies.")
        else:
            print(f"[WARNING] ProxyManager: Refresh failed (0 valid proxies). Keeping {len(self.proxies)} from cache.")
            # Trigger smaller REFRESH_INTERVAL to try again sooner if we are empty
            if not self.proxies:
                 self.last_refresh = time.time() - (self.REFRESH_INTERVAL - 300) # retry in 5 mins

proxy_manager = ProxyManager()
