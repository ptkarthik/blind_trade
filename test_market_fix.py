
import asyncio
import sys
import os
import time

# Ensure backend dir is in path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.market_data import market_service

async def test_market_service():
    print("Testing MarketDataService with New Timeout Logic...")
    
    start = time.time()
    status = await market_service.get_market_status()
    end = time.time()
    print(f"Market Status: {status} (Took {end-start:.2f}s)")
    
    start = time.time()
    ad_ratio = await market_service.get_advance_decline_ratio()
    end = time.time()
    print(f"A/D Ratio: {ad_ratio} (Took {end-start:.2f}s)")
    
    print("Testing Live Price fetch for RELIANCE.NS...")
    start = time.time()
    price = await market_service.get_live_price("RELIANCE.NS")
    end = time.time()
    print(f"Price Data: {price.get('price')} from {price.get('source')} (Took {end-start:.2f}s)")

if __name__ == "__main__":
    asyncio.run(test_market_service())
