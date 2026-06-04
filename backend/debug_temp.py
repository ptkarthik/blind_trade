import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
import asyncio
from app.services.market_data import market_service
from app.services.kite_data import kite_data

async def main():
    await kite_data.initialize()
    print('Kite ready:', kite_data.is_ready)
    res = await market_service.get_batch_ohlc(['RELIANCE.NS'], interval='1d', period='1mo')
    print("RES keys:", res.keys())

asyncio.run(main())
