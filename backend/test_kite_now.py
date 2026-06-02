import asyncio
from app.services.kite_data import kite_data

async def main():
    await kite_data.initialize()
    if not kite_data.is_ready:
        print("Kite is NOT ready!")
        return
        
    df = await kite_data.fetch_ohlc("RELIANCE.NS", period="1y", interval="1d")
    print(f"RELIANCE: {len(df)} candles fetched.")
    
    df2 = await kite_data.fetch_ohlc("BLSE.NS", period="1y", interval="1d")
    print(f"BLSE: {len(df2)} candles fetched.")
    
asyncio.run(main())
