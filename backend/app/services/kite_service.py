import requests
import json
import os
import time
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class KiteMarginService:
    """
    [V14.0] Institutional Tradability Auditor for Kite (Zerodha).
    Automatically fetches and caches the Zerodha Margin list to identify MIS-blocked stocks.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(KiteMarginService, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
            
        self.margin_url = "https://api.kite.trade/margins/equity"
        self.cache_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kite_margin_cache.json")
        self.allowed_symbols = {} 
        self.last_updated = None
        
        # [V14.1] Self-Healing: Load from cache immediately if exists
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                    self.allowed_symbols = cache_data.get("symbols", {})
                    self.last_updated = datetime.fromisoformat(cache_data.get("timestamp", "2000-01-01"))
            except: pass
            
        self.initialized = True
        
    async def initialize(self):
        """Bootstraps the margin cache at engine start."""
        await self.sync_margins()

    async def sync_margins(self, force=False):
        """Syncs Zerodha margins with local cache."""
        now = datetime.now()
        
        # 1. Load from cache if valid
        if not force and os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    cache_data = json.load(f)
                    ts = datetime.fromisoformat(cache_data.get("timestamp", "2000-01-01"))
                    if (now - ts) < timedelta(hours=24):
                        self.allowed_symbols = cache_data.get("symbols", {})
                        self.last_updated = ts
                        logger.info(f"️ KiteMarginService: Loaded {len(self.allowed_symbols)} symbols from cache.")
                        return
            except Exception as e:
                logger.warning(f"️ KiteMarginService: Cache corrupt, re-fetching. {e}")

        # 2. Fetch fresh from Zerodha
        try:
            logger.info(" KiteMarginService: Synchronizing with Zerodha Margin API...")
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(self.margin_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                # Create a fast lookup map: SYMBOL -> Multiplier
                # Note: Zerodha uses raw symbols like 'RELIANCE', our engine uses 'RELIANCE.NS'
                mapping = {}
                for item in data:
                    sym = item.get("tradingsymbol")
                    mult = item.get("mis_multiplier", 1.0)
                    if sym:
                        mapping[sym] = float(mult)
                
                self.allowed_symbols = mapping
                self.last_updated = now
                
                # Save to cache
                with open(self.cache_file, "w") as f:
                    json.dump({
                        "timestamp": now.isoformat(),
                        "symbols": mapping
                    }, f)
                
                logger.info(f" KiteMarginService: Synchronized {len(mapping)} symbols (Source: Zerodha).")
            else:
                logger.error(f" KiteMarginService: Failed fetch ({response.status_code})")
        except Exception as e:
            logger.error(f" KiteMarginService: Sync Error: {e}")

    def get_tradability(self, symbol: str) -> dict:
        """
        Audits a symbol for Kite intraday tradability.
        Returns: { 'is_kite_restricted': bool, 'multiplier': float }
        """
        # Clean the symbol (RELIANCE.NS -> RELIANCE)
        raw_sym = symbol.split(".")[0].upper()
        
        # If not in list, it is restricted (CNC Only)
        if raw_sym not in self.allowed_symbols:
            return {"is_kite_restricted": True, "multiplier": 1.0, "reason": "Not in margin list (CNC Only)"}
        
        multiplier = self.allowed_symbols[raw_sym]
        
        # If multiplier is 1.0, it's delivery only (No leverage)
        if multiplier <= 1.0:
            return {"is_kite_restricted": True, "multiplier": 1.0, "reason": "No leverage allowed (CNC Only)"}
            
        return {"is_kite_restricted": False, "multiplier": multiplier, "reason": "Intraday Allowed"}

# Singleton Instance
kite_service = KiteMarginService()
