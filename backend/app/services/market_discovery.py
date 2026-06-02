import pandas as pd
import requests
import os
import io
import time
from typing import List, Dict

class MarketDiscoveryService:
    def __init__(self):
        self.NSE_EQUITY_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.cache_file = os.path.join(self.cache_dir, "nse_market_list.json")
        self.CACHE_DURATION = 86400 # 24 hours
        
    def _fetch_nse_list(self) -> List[Dict]:
        """Fetches the official CSV from NSE and parses symbols."""
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/csv,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        try:
            # [V12.2] NSE requires specific headers to prevent 403/stalls
            response = session.get(self.NSE_EQUITY_URL, headers=headers, timeout=10)
            response.raise_for_status()
            
            df = pd.read_csv(io.StringIO(response.text))
            stocks = []
            for _, row in df.iterrows():
                symbol = str(row['SYMBOL']).strip()
                name = str(row['NAME OF COMPANY']).strip()
                series = str(row[' SERIES']).strip()
                
                # FIX #5: Only EQ series — BE (Trade-for-Trade) stocks CANNOT be traded intraday
                # OLD: allowed both 'EQ' and 'BE', wasting ~15% of scan capacity on blocked stocks
                # BE stocks are restricted by SEBI and blocked by all major brokers for MIS/intraday
                if series == 'EQ':
                    stocks.append({
                        "symbol": f"{symbol}.NS",
                        "name": name,
                        "raw_symbol": symbol,
                        "industry": str(row.get(' INDUSTRY', 'General')).strip()
                    })
            # [V26 V6-FIX 2] KITE MARGIN FILTER (Scrub Intraday Blocked EQ Stocks)
            try:
                margin_res = session.get("https://api.kite.trade/margins/equity", timeout=5)
                margin_res.raise_for_status()
                kite_margins = margin_res.json()
                
                # Check for mis_multiplier > 0.0 or mis_margin < 100 which indicates MIS is allowed
                mis_allowed = {
                    item['tradingsymbol']: item 
                    for item in kite_margins 
                    if item.get('mis_multiplier', 0) > 0.0 or item.get('mis_margin', 100) < 100
                }
                
                tradable_stocks = []
                for stock in stocks:
                    if stock['raw_symbol'] in mis_allowed:
                        tradable_stocks.append(stock)
                
                if len(tradable_stocks) > 100:
                    stocks = tradable_stocks
            except Exception as e:
                print(f"[WARN] MarketDiscovery: Kite MIS Sync Failed, proceeding with raw list: {e}")
                
            return stocks
        except Exception as e:
            print(f"[WARN] MarketDiscovery: Fetch failed (Network/NSE): {e}")
            return []
        finally:
            session.close()

    async def get_full_market_list(self) -> List[Dict]:
        """Returns the full list of NSE stocks, using cache if valid."""
        import json
        
        # 1. Check Cache
        if os.path.exists(self.cache_file):
            mtime = os.path.getmtime(self.cache_file)
            if (time.time() - mtime) < self.CACHE_DURATION:
                try:
                    with open(self.cache_file, "r") as f:
                        cached = json.load(f)
                    # [V31 GAP#14] Apply dead stock filter even on cached list
                    return self._filter_dead_stocks(cached)
                except: pass
        
        # 2. Fetch Fresh
        print("[DISCOVERY] MarketDiscovery: Fetching fresh NSE equity list...")
        import asyncio
        stocks = await asyncio.to_thread(self._fetch_nse_list)
        
        if stocks:
            try:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(self.cache_file, "w") as f:
                    json.dump(stocks, f, indent=4)
            except Exception as e:
                print(f"MarketDiscovery: Cache save failed: {e}")
            
            # [V31 GAP#14] Filter dead stocks before returning
            return self._filter_dead_stocks(stocks)
            
        return []
    
    def _filter_dead_stocks(self, stocks: List[Dict]) -> List[Dict]:
        """[V31 GAP#14] Remove suspended/dead stocks using liquidity cache.
        
        Stocks that returned zero ADV20 in prior scans are almost certainly
        suspended, delisted, or under ASM/GSM restrictions. Scanning them
        wastes ~10s each (timeout) and never produces signals.
        """
        try:
            # Load liquidity cache to check for known dead stocks
            liq_cache_path = os.path.join(self.cache_dir, "liquidity_master.json")
            if not os.path.exists(liq_cache_path):
                return stocks  # No prior data, can't filter
            
            import json
            with open(liq_cache_path, "r") as f:
                liq_data = json.load(f)
            
            if not liq_data:
                return stocks
            
            original_count = len(stocks)
            filtered = []
            removed_count = 0
            
            for stock in stocks:
                sym = stock.get("symbol", "")
                liq = liq_data.get(sym, {})
                adv20 = liq.get("adv20", -1)  # -1 means never scanned (keep it)
                
                # Remove only stocks that were scanned AND returned zero volume
                # adv20 == 0 means Yahoo returned data but volume was 0 = suspended
                if adv20 == 0:
                    removed_count += 1
                    continue
                
                # Also remove stocks with extremely low turnover (< ₹10L daily)
                # These can't be traded intraday without major slippage
                level = liq.get("level", "Unknown")
                if level == "Very Low" and adv20 > 0:
                    removed_count += 1
                    continue
                
                filtered.append(stock)
            
            if removed_count > 0:
                print(f"[GAP#14] Filtered {removed_count} dead/illiquid stocks ({original_count} -> {len(filtered)})")
            
            return filtered
        except Exception as e:
            print(f"[WARN] MarketDiscovery: Dead stock filter failed: {e}")
            return stocks  # Fail-open: return all stocks if filter crashes

market_discovery = MarketDiscoveryService()
