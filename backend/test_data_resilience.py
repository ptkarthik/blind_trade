import asyncio
import pandas as pd
import time
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.market_data import MarketDataService

async def test_resilience():
    service = MarketDataService()
    symbol = "RELIANCE.NS"
    
    print("\n--- Testing OHLC Caching ---")
    start_time = time.time()
    df1 = await service.get_ohlc(symbol, period="1d", interval="15m")
    duration1 = time.time() - start_time
    print(f"First fetch (Network): {duration1:.2f}s, Rows: {len(df1)}")
    
    start_time = time.time()
    df2 = await service.get_ohlc(symbol, period="1d", interval="15m")
    duration2 = time.time() - start_time
    print(f"Second fetch (Cache): {duration2:.2f}s, Rows: {len(df2)}")
    
    if duration2 < duration1 and not df2.empty:
        print("✅ OHLC Caching Verified.")
    else:
        print("❌ OHLC Caching Failed.")

    print("\n--- Testing Live Price Caching & Retries ---")
    start_time = time.time()
    p1 = await service.get_live_price(symbol)
    duration1 = time.time() - start_time
    print(f"Live Price fetch 1: {duration1:.2f}s, Price: {p1.get('price')}")
    
    start_time = time.time()
    p2 = await service.get_live_price(symbol)
    duration2 = time.time() - start_time
    print(f"Live Price fetch 2 (Cache): {duration2:.2f}s, Price: {p2.get('price')}")
    
    if duration2 < 0.1:
        print("✅ Live Price Caching Verified.")
    else:
        print("❌ Live Price Caching Failed.")

    print("\n--- Testing Defensive Validation ---")
    # We can't easily force a bad response from YF, but we can check if a non-existent symbol is handled
    bad_sym = "NONEXISTENT_TICKER_XYZ"
    res = await service.get_ohlc(bad_sym, period="1d", interval="1d")
    if isinstance(res, pd.DataFrame) and res.empty:
         print(f"✅ Graceful failure for {bad_sym} verified.")
    else:
         print(f"❌ Graceful failure failed for {bad_sym}.")

    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(test_resilience())
