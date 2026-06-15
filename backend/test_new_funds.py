import asyncio
from app.services.market_data import market_service
from app.services.fundamentals import fundamental_engine

async def test():
    await market_service.initialize()
    info = await market_service.get_fundamentals("TCS")
    res = fundamental_engine.analyze(info, None)
    print("SCORE:", res['score'])
    print("DETAILS:", [d['text'] for d in res['details'] if d['label'] in ['YIELD', 'ESTIMATES']])
    
asyncio.run(test())
