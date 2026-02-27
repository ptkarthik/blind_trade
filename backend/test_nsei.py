import asyncio
from app.services.market_data import market_service
import time

async def test():
    t0 = time.time()
    print("Fetching NIFTY 15m data...")
    df = await market_service.get_ohlc("^NSEI", period="2d", interval="15m")
    t1 = time.time()
    print(f"Done in {t1-t0:.2f}s")
    if not df.empty:
        print("Data length:", len(df))
    else:
        print("Data is empty")

if __name__ == "__main__":
    asyncio.run(test())
