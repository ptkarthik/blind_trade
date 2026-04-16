import asyncio
from app.services.market_data import market_service
from app.services.swing_engine import swing_engine

async def run():
    print("Testing backend logic...")
    await swing_engine.refresh_market_context()
    res = await swing_engine.analyze_stock('RELIANCE.NS')
    print("Analyzed RELIANCE.NS:")
    print(res)
    
    df = await market_service.get_ohlc('RELIANCE.NS', period='1y', interval='1d')
    print("Latest Date in DF:", df.index[-1])
    
    from datetime import datetime, timedelta
    import pandas as pd
    latest_date = pd.to_datetime(df.index[-1])
    if latest_date.tzinfo is not None:
         latest_date = latest_date.tz_convert(None)
    
    diff = datetime.utcnow() - latest_date
    print(f"Hours Stale: {diff.total_seconds() / 3600}")

if __name__ == "__main__":
    asyncio.run(run())
