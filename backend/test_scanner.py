import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    res = await engine.analyze_stock("TCS")
    if res:
        print("SCORE:", res.get("score"))
        inst = res.get("details", [])
        for t in inst:
            print("TAG:", t)

asyncio.run(test())
