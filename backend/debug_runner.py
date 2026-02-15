import asyncio
import sys
import os
import time

# Add current dir to path
sys.path.append(os.getcwd())

from app.api.api_v1.endpoints.signals import get_todays_signals
from app.services.market_data import market_service

async def main():
    print("--- Starting Debug Run ---")
    start = time.time()
    
    # Force initialize (normally done on startup)
    # await market_service.initialize() 
    
    print("Calling get_todays_signals('intraday')...")
    try:
        signals = await get_todays_signals(mode="intraday")
        duration = time.time() - start
        print(f"--- Finished in {duration:.2f} seconds ---")
        print(f"Signals found: {len(signals)}")
        for s in signals:
            print(f"  {s['symbol']}: {s['signal']} (Score: {s['score']})")
    except Exception as e:
        print(f"CRITICAL FAILURE: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
