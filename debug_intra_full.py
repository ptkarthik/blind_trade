
import sys
import os
import asyncio
import logging

# Setup Logging to Console
logging.basicConfig(level=logging.INFO)

# Fix Path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.intraday_engine import intraday_engine
from app.services.market_data import market_service

async def trace_analysis(symbol):
    print(f"\n--- TRACING ANALYSIS FOR {symbol} ---")
    
    # 1. Check Data Availability
    print("1. Fetching OHLC 15m...")
    try:
        df_15m = await market_service.get_ohlc(symbol, period="5d", interval="15m")
        print(f"   Shape: {df_15m.shape}")
        if df_15m.empty:
            print("   ❌ FAIL: Empty 15m Data")
            return
        print(f"   Rows: {len(df_15m)}")
    except Exception as e:
        print(f"   ❌ FAIL: Exception fetching 15m: {e}")
        return

    print("2. Fetching Live Price...")
    try:
        price_data = await market_service.get_live_price(symbol)
        print(f"   Price: {price_data.get('price')}")
    except Exception as e:
        print(f"   ❌ FAIL: Exception fetching price: {e}")
        return

    # 3. Run Engine Analysis
    print("3. Running intraday_engine.analyze_stock()...")
    try:
        result = await intraday_engine.analyze_stock(symbol)
        if result:
            print("   ✅ SUCCESS: Result returned")
            print(f"   Score: {result.get('score')}")
            print(f"   Verdict: {result.get('verdict')}")
        else:
            print("   ❌ FAIL: analyze_stock returned None (Check engine filters)")
            
    except Exception as e:
        print(f"   ❌ FAIL: Engine Exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(trace_analysis("RELIANCE.NS"))
