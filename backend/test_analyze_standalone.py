
import asyncio
import pandas as pd
from app.services.scanner_engine import longterm_scanner_engine
import time

async def test_analysis():
    symbol = "ZOMATO.NS"
    print(f"Testing Analysis for {symbol}...")
    start = time.time()
    try:
        # We call the internal analyze_stock directly
        res = await longterm_scanner_engine.analyze_stock(symbol)
        end = time.time()
        print(f"Analysis Finished in {end-start:.2f}s")
        if res:
            print(f"Result for {symbol}: Score={res.get('score')}, Signal={res.get('signal')}")
        else:
            print(f"Result for {symbol}: None (Data probably missing)")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Analysis Crashed: {e}")

if __name__ == "__main__":
    asyncio.run(test_analysis())
