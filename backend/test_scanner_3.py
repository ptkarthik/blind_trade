import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    
    # We pass 'TCS.NS' to be safe with yfinance
    res = await engine.analyze_stock("TCS.NS")
    if res:
        print("SCORE:", res.get("score"))
        inst = res.get("details", [])
        print("TAGS:", [t for t in inst if 'RS' in str(t['label']) or 'YIELD' in str(t['label'])])
    else:
        print("FAILED TO ANALYZE TCS")

asyncio.run(test())
