
import asyncio
import os
import sys
from twelvedata import TDClient

# Load settings to get API key
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))
from backend.app.core.config import settings

async def test_td():
    print(f"--- 🛰️ TwelveData Raw Stream Test ---")
    key = settings.MARKET_DATA_API_KEY
    if not key:
        print("❌ No API Key found in settings!")
        return
    
    td = TDClient(apikey=key)
    # Test symbol: BANKBARODA
    symbol = "BANKBARODA:NSE"
    print(f"📡 Requesting RAW price for {symbol}...")
    
    try:
        def _fetch():
            return td.price(symbol=symbol).as_json()
        
        res = await asyncio.to_thread(_fetch)
        print(f"📥 RAW Response: {res}")
        
    except Exception as e:
        print(f"❌ TD Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_td())
