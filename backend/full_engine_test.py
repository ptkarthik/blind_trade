import asyncio
import time
from app.services.market_data import market_service

async def stress_test():
    await market_service.initialize()
    # Test batch of 100 symbols
    # We'll just take the top 100 from the master list
    symbols = [s["symbol"] for s in market_service.stock_master[:100]]
    
    print(f"🚀 [STRESS TEST] Starting Full Engine Scan for {len(symbols)} symbols...")
    start_time = time.time()
    
    # Run the actual batch logic used by the engine
    results = await market_service.get_batch_ohlc(symbols, period="7d", interval="15m")
    
    end_time = time.time()
    total_time = end_time - start_time
    
    print(f"\n--- Results ---")
    print(f"📦 Successfully fetched: {len(results)}/{len(symbols)}")
    print(f"⏱️ Total Time: {total_time:.2f} seconds")
    print(f"⚡ Average Speed: {len(symbols)/total_time:.2f} symbols/sec")
    
    if len(results) > 0:
        first_key = list(results.keys())[0]
        print(f"✅ Data Sample ({first_key}):")
        print(results[first_key].tail(2))

if __name__ == "__main__":
    asyncio.run(stress_test())
