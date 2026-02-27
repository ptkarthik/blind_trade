
import asyncio
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.services.market_data import market_service
import yfinance as yf

async def test_fast():
    symbol = "RELIANCE.NS"
    print(f"Testing fast_info for {symbol}...")
    try:
        # 1. Via Service (which uses fast_info primarily)
        price = await market_service.get_latest_price(symbol)
        print(f"Service Price: {price}")
        
        # 2. Direct YF
        t = yf.Ticker(symbol)
        fi = t.fast_info
        print(f"Direct FastInfo: {fi.last_price}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_fast())
