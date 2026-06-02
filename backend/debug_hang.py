import sys
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
import asyncio
from app.services.market_data import market_service
from app.services.kite_data import kite_data

async def main():
    await kite_data.initialize()
    symbols = ["PRESTIGE.NS", "CARBORUNIV.NS"]
    print("Testing get_batch_ohlc 15m")
    r1 = await market_service.get_batch_ohlc(symbols, interval="15m", period="7d")
    print("15m done")
    print("Testing get_batch_ohlc 60m")
    r2 = await market_service.get_batch_ohlc(symbols, interval="60m", period="15d")
    print("60m done")
    print("Testing get_batch_ohlc 1d")
    r3 = await market_service.get_batch_ohlc(symbols, interval="1d", period="3mo")
    print("1d done")
    print("Testing get_batch_prices")
    r4 = await market_service.get_batch_prices(symbols)
    print("prices done")
    print("Testing get_market_depth")
    r5 = await kite_data.get_market_depth(symbols)
    print("depth done")
    print("All done")

asyncio.run(main())
