
import asyncio
import pandas as pd
from app.services.market_data import market_service
from app.services.intraday_engine import intraday_engine
import os

# Set up environment
os.environ["PYTHONPATH"] = os.getcwd()

async def test_intraday_zomato():
    symbol = "ZOMATO.NS"
    print(f"\n--- Testing Intraday Data for {symbol} ---\n")
    
    # 1. Test 15m OHLC
    print(f"Fetching 15m OHLC (5d)...")
    try:
        df_15m = await market_service.get_ohlc(symbol, period="5d", interval="15m")
        print(f"15m Data: {len(df_15m)} rows")
        if not df_15m.empty:
            print(f"Last 15m close: {df_15m['close'].iloc[-1]}")
    except Exception as e:
        print(f"15m Fetch Error: {e}")

    # 2. Test 5m OHLC
    print(f"\nFetching 5m OHLC (2d)...")
    try:
        df_5m = await market_service.get_ohlc(symbol, period="2d", interval="5m")
        print(f"5m Data: {len(df_5m)} rows")
    except Exception as e:
        print(f"5m Fetch Error: {e}")

    # 3. Test Live Price
    print(f"\nFetching Live Price...")
    try:
        price_data = await market_service.get_live_price(symbol)
        print(f"Price Data: {price_data}")
    except Exception as e:
        print(f"Live Price Error: {e}")

    # 4. Test Index Context
    print(f"\nFetching Index Context...")
    try:
        # Note: _get_index_context is an internal method, we can test its parts or just call it if public-ish
        from app.services.intraday_engine import intraday_engine
        index_ctx = await intraday_engine._get_index_context()
        print(f"Index Context: {index_ctx}")
    except Exception as e:
        print(f"Index Context Error: {e}")

    # 5. Full Engine Run
    print(f"\nRunning Full Intraday Engine Analyze...")
    try:
        res = await intraday_engine.analyze_stock(symbol)
        if res:
            print(f"Analysis Success! Score: {res.get('score')}")
        else:
            print("Analysis Failed (Returned None)")
    except Exception as e:
        print(f"Engine Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_intraday_zomato())
