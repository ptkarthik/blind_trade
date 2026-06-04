import asyncio
from app.services.swing_engine import swing_engine
from app.services.kite_data import kite_data

async def test():
    await kite_data.initialize()
    if not kite_data.is_ready:
        print("Kite not ready")
        return
        
    print("Fetching swing OHLC for RELIANCE.NS via evasion fetcher...")
    df = await swing_engine._fetch_swing_ohlc_with_evasion("RELIANCE.NS", period="1y", interval="1d")
    if df is not None and not df.empty:
        print("Success! Got DataFrame with shape:", df.shape)
        print(df.tail(2))
    else:
        print("Failed to fetch data.")

if __name__ == "__main__":
    asyncio.run(test())
