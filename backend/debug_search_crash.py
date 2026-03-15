
import asyncio
from app.services.intraday_engine import intraday_engine

async def debug_cchhl():
    symbol = "CCHHL.NS"
    print(f"Debugging Analysis for {symbol}...")
    try:
        res = await intraday_engine.analyze_stock(symbol, fast_fail=True)
        if res:
            print(f"Success! Score: {res.get('score')}")
        else:
            print("Engine returned None")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Crash detected: {e}")

if __name__ == "__main__":
    asyncio.run(debug_cchhl())
