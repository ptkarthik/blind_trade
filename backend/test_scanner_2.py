import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service
from app.services.fundamentals import fundamental_engine

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    
    # Let's do it step by step to see where it breaks
    fund_data = await market_service.get_fundamentals("TCS")
    fund_res = fundamental_engine.analyze(fund_data, None)
    print("FUND DETAILS:", fund_res.get("details"))

asyncio.run(test())
