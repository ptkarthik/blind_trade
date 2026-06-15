import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    
    res = await engine.analyze_stock("TCS.NS")
    if res:
        print("REASONS:", res.get("reasons", []))
        print("GROUPS:", res.get("groups", {}))

asyncio.run(test())
