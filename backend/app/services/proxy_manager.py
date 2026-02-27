
import asyncio
import requests
import random
import time
import urllib3
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
            "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt"
        ]

    async def get_proxy(self) -> Optional[str]:
        """
        Returns a valid proxy from the pool.
        Triggers a refresh if the pool is empty or stale.
        """
        async with self.lock:
            # excessive refreshing protection
            if not self.proxies or (time.time() - self.last_refresh > self.REFRESH_INTERVAL):
                await self._refresh_proxies()
            
            if not self.proxies:
                return None
                
            # Random selection for distribution (better than round robin for free proxies)
            return random.choice(self.proxies)

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
        print("🔄 ProxyManager: Refreshing Proxy List (Threaded)...")
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

        print(f"🔎 Found {len(raw_proxies)} raw proxies. Validating...")
        
        # 2. Validate (Batch processing)
        candidates = list(raw_proxies - self.blacklist_set)
        random.shuffle(candidates)
        candidates = candidates[:300] 
        
        valid_proxies = []
        
        def validate_sync(proxy):
            # Using a more reliable target for basic network check
            target_url = "https://www.google.com" 
            try:
                resp = requests.get(target_url, proxies={"http": proxy, "https": proxy}, timeout=8, verify=False)
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
        
        self.proxies = valid_proxies
        self.last_refresh = time.time()
        self.blacklist_set.clear() # Reset blacklist on new fetch
        print(f"✅ ProxyManager: Activated {len(self.proxies)} working proxies.")

proxy_manager = ProxyManager()
