import asyncio
import sys
import os

sys.path.append(os.getcwd())
from app.services.market_data import market_service

async def main():
    df = await market_service.get_ohlc('DHANUKA.NS', '2d', '15m')
    if df is not None and len(df) > 0:
        print("Last index:", df.index[-1])
        print("Hour:", df.index[-1].hour)
        print("Timezone:", df.index[-1].tz)
    else:
        print("No data")

asyncio.run(main())
