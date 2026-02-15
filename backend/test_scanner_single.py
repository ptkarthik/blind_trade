
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_single():
    symbol = "RELIANCE"
    print(f"--- Testing Scanner for {symbol} ---")
    
    # 1. Test Market Data directly
    print("\n1. Market Data Check:")
    df = await market_service.get_ohlc(symbol, period="5y", interval="1wk")
    price = await market_service.get_live_price(symbol)
    print(f"   OHLC Rows: {len(df)}")
    print(f"   Live Price: {price.get('price')}")
    
    if df.empty:
        print("   ❌ OHLC is EMPTY. Scanner will abort.")
    
    # 2. Test Analyze Stock
    print("\n2. Full Analysis Check:")
    try:
        res = await scanner_engine.analyze_stock(symbol)
        if res:
            print("   ✅ Analysis Success!")
            print(f"   Score: {res.get('score')}")
        else:
            print("   ❌ Analysis returned None (Silent Failure).")
    except Exception as e:
        print(f"   ❌ Analysis Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Initialize DB (needed for some services? No, scanner mainly uses API)
    # But we need asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_single())
