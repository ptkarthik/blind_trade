
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
import asyncio
import pandas as pd
from app.services.market_data import market_service

async def test_fetch():
    symbol = "RELIANCE.NS"
    print(f"Fetching 15m OHLC for {symbol} (Testing 5m + Download Fallback)...")
    
    try:
        # We need to call get_ohlc which has the new logic
        df = await market_service.get_ohlc(symbol, period="5d", interval="15m")
        print(f"Result Shape: {df.shape}")
        if not df.empty:
            print("Head (Check time interval):")
            print(df.head())
        else:
            print("❌ DataFrame is Empty (Download fallback failed too)!")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_fetch())
