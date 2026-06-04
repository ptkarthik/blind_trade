import asyncio
import sys
import os
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine
from app.services.market_discovery import market_discovery

async def main():
    print("Mocking market discovery to only return 5 symbols for speed...", flush=True)
    # Monkey patch market_discovery to be fast
    async def fast_get_list():
        return [{"symbol": "RELIANCE.NS"}, {"symbol": "TCS.NS"}, {"symbol": "INFY.NS"}, {"symbol": "HDFCBANK.NS"}, {"symbol": "ICICIBANK.NS"}]
    
    market_discovery.get_full_market_list = fast_get_list
    
    job_id = "test_fast"
    swing_engine.start_job(job_id)
    
    try:
        results = await swing_engine.run_scan(job_id)
        print("Done!", flush=True)
        print("Data count:", len(results.get("data", [])))
    except Exception as e:
        print("CRASHED:", e)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
