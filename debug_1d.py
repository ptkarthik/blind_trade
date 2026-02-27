import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import asyncio
from app.services.market_data import market_service

async def test_1d():
    symbol = "RELIANCE.NS"
    print(f"Fetching 1d OHLC for {symbol}...")
    try:
        df = await market_service.get_ohlc(symbol, period="1mo", interval="1d")
        print(f"Result Shape: {df.shape}")
        if not df.empty:
            print(df.head())
        else:
            print("❌ 1d Data is Empty")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_1d())
