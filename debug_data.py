import asyncio
from app.services.market_data import market_service
import pandas as pd

async def test_fetch():
    symbol = "INFY.NS"
    print(f"Testing 15m fetch for {symbol}...")
    try:
        df = await market_service.get_ohlc(symbol, period="5d", interval="15m")
        print(f"Result Shape: {df.shape}")
        if df.empty:
            print("❌ DataFrame is Empty (Download fallback failed too)!")
        else:
            print("✅ Data Fetched Successfully!")
            print(df.tail())
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
