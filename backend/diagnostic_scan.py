import asyncio
import pandas as pd
from app.services.intraday_engine import IntradayEngine
from app.services.market_data import market_service
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnostic")

async def run_diagnostic():
    engine = IntradayEngine()
    symbols = ["RELIANCE.NS", "TCS.NS", "ZOMATO.NS"]
    
    print(f"Running diagnostic scan for {symbols}...")
    
    # 1. Manually fetch market context if possible
    index_ctx = {"market_regime": "BULLISH"}
    
    results = []
    for sym in symbols:
        try:
            print(f"\n--- Analyzing {sym} ---")
            # We bypass the batch logic to see direct results
            res = await engine.analyze_stock(sym, global_index_ctx=index_ctx)
            
            if "skip_reason" in res:
                print(f"SKIP REASON for {sym}: {res['skip_reason']}")
            else:
                print(f"SUCCESS Choice for {sym}: Score={res['score']}, Signal={res['signal']}")
                results.append(res)
        except Exception as e:
            print(f"CRITICAL FAILURE for {sym}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nFinal Results Count: {len(results)}")

if __name__ == "__main__":
    asyncio.run(run_diagnostic())
