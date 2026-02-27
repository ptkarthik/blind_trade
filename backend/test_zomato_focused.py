
import asyncio
import pandas as pd
from app.services.market_data import market_service

async def test_zomato():
    print("Testing ZOMATO.NS Data Retrieval...")
    try:
        price = await market_service.get_live_price("ZOMATO.NS")
        print(f"Price Result: {price}")
        
        ohlc = await market_service.get_ohlc("ZOMATO.NS", period="5d", interval="15m")
        print(f"OHLC Rows: {len(ohlc)}")
        if not ohlc.empty:
            print(ohlc.tail(2))
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_zomato())
