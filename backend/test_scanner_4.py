import asyncio
from app.services.scanner_engine import LongTermScannerEngine
from app.services.market_data import market_service
from app.services.fundamentals import fundamental_engine

async def test():
    await market_service.initialize()
    engine = LongTermScannerEngine()
    
    # Do exactly what analyze_stock does
    sym = "TCS.NS"
    fund_task = market_service.get_fundamentals(sym)
    hist_fin_task = market_service.get_historical_financials(sym)
    
    results = await asyncio.gather(fund_task, hist_fin_task)
    fund_data = results[0]
    hist_financials = results[1]
    
    fund_res = fundamental_engine.analyze(fund_data, hist_financials)
    print("FUND DETAILS:", fund_res.get("details"))

asyncio.run(test())
