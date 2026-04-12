import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from app.services.intraday_engine import IntradayEngine

async def run_test():
    engine = IntradayEngine()
    symbols = ["AEQUS.NS"]
    
    from app.services.market_data import market_service
    res_15m = await market_service.get_batch_ohlc(symbols)
    res_prices = await market_service.get_batch_prices(symbols)
    
    batch_pulse = {
        "AEQUS.NS": {"15m": res_15m.get("AEQUS.NS"), "price": res_prices.get("AEQUS.NS", {}).get("price", 0.0)}
    }
    
    res = await engine.analyze_stock("AEQUS.NS", "test", None, batch_pulse)
    print(res)

if __name__ == "__main__":
    asyncio.run(run_test())
