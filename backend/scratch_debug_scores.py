import sys
import os
import io

# Prevent Unicode errors on Windows terminal
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.getcwd())

import asyncio
import json
import traceback
from app.services.intraday_engine import intraday_engine
from app.services.index_context import index_ctx
from app.services.yahoo_fast import yahoo_fast

async def main():
    symbols = ["APLLTD.NS", "APOLLO.NS"]
    
    print(f"Fetching data for {symbols}...")
    # fetch_batch is async in the new yahoo_fast version? Let's check its signature.
    # Ah, fetch_batch uses ThreadPoolExecutor internally, but wait, is it an async function?
    # Let's use asyncio.to_thread if it's sync. Let's assume it's sync or async, let's just check.
    import inspect
    print("Fetching 15m...")
    data_15m = await yahoo_fast.fetch_batch(symbols, "15m", "5d")
    print("Fetching 5m...")
    data_5m = await yahoo_fast.fetch_batch(symbols, "5m", "5d")
    print("Fetching 1h...")
    data_1h = await yahoo_fast.fetch_batch(symbols, "1h", "20d")
    
    intraday_engine.data_cache = {
        "15m": data_15m,
        "5m": data_5m,
        "1h": data_1h
    }
    
    for sym in symbols:
        print(f"\n=====================================")
        print(f"ANALYZING {sym}")
        print(f"=====================================")
        
        # Check data shape
        df_15 = data_15m.get(sym)
        df_5 = data_5m.get(sym)
        df_1h = data_1h.get(sym)
        
        print(f"Data shapes - 15m: {df_15.shape if df_15 is not None else 'None'}, 5m: {df_5.shape if df_5 is not None else 'None'}, 1h: {df_1h.shape if df_1h is not None else 'None'}")
        
        try:
            res = await intraday_engine.analyze_stock(sym, "test_job_123", index_ctx, {}, {})
            if res:
                print(f"\nFinal Score: {res.get('score')}")
                print(f"Skip Reason: {res.get('skip_reason', 'None')}")
                if "groups" in res:
                    print("\nScoring Groups:")
                    for grp, grp_data in res["groups"].items():
                        print(f"  {grp}: {grp_data.get('score', 0)}")
                
                if "reasons" in res:
                    print("\nScore Breakdown:")
                    for r in res["reasons"]:
                        print(f"  [{r.get('impact', 0):>4}] {r.get('text')}")
                
                print("\nIndicators Snapshot:")
                inds = res.get("indicators", {})
                for k, v in inds.items():
                    print(f"  {k}: {v}")
            else:
                print(f"No result returned for {sym}")
        except Exception as e:
            print(f"Error analyzing {sym}: {e}")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
