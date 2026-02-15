
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.market_data import market_service

async def test_fetch():
    print("--- Testing Market Data Fix ---")
    
    # Test 1: Index (Should NOT have .NS)
    symbol = "^NSEI"
    print(f"\n1. Fetching {symbol}...")
    # we can't easily access the internal ticker_symbol variable, 
    # but we can see if it works or fails with "No data found".
    df = await market_service.get_ohlc(symbol, period="5d")
    if not df.empty:
        print(f"✅ Success! {symbol} returned {len(df)} rows.")
    else:
        print(f"❌ Failed! {symbol} returned empty DataFrame.")

    # Test 2: Stock (Should HAVE .NS)
    symbol = "RELIANCE"
    print(f"\n2. Fetching {symbol}...")
    df = await market_service.get_ohlc(symbol, period="5d")
    if not df.empty:
        print(f"✅ Success! {symbol} returned {len(df)} rows.")
    else:
        print(f"❌ Failed! {symbol} returned empty DataFrame.")

if __name__ == "__main__":
    try:
        asyncio.run(test_fetch())
    except Exception as e:
        print(f"Test Error: {e}")
