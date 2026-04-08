
import asyncio
import os
import sys

# Add root and backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.app.services.market_data import MarketDataService

async def check():
    print("--- 🛰️ TwelveData Pulse Test (Real-Time) ---")
    m = MarketDataService()
    await m.initialize()
    
    symbol = "INDIANB.NS"
    print(f"📡 Fetching live quote for {symbol}...")
    
    try:
        # We test the batch fetcher since it's what the UI uses
        res = await m.get_batch_prices([symbol])
        print(f"✅ Pulse Result: {res}")
        
        if symbol in res:
            price = res[symbol].get("price", 0)
            if price > 0:
                print(f"💰 SUCCESS! Live Price for {symbol} is ₹{price}")
            else:
                print(f"⚠️ Warning: Price is 0 or malformed.")
        else:
            print(f"❌ Failure: Symbol not in batch result.")
            
    except Exception as e:
        print(f"❌ Crash during fetch: {e}")

if __name__ == "__main__":
    asyncio.run(check())
