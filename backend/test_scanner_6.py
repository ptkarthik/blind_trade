import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    
    # We pass 'TCS.NS'
    res = await engine.analyze_stock("TCS.NS")
    if res:
        print("ALL DETAILS:", res.get("details", []))

asyncio.run(test())
