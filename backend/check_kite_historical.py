import asyncio
import datetime
from app.services.kite_data import kite_data

async def test_hist():
    await kite_data.initialize()
    if not kite_data.is_ready:
        print("Kite is not ready.")
        return
    kite = kite_data._kite
    to_dt = datetime.datetime.now()
    from_dt = to_dt - datetime.timedelta(days=5)
    
    # 256265 is the instrument token for NIFTY 50
    try:
        data = kite.historical_data(256265, from_dt, to_dt, 'day')
        print("Historical API works! Data points:", len(data))
    except Exception as e:
        print("Error fetching historical data:", e)

if __name__ == "__main__":
    asyncio.run(test_hist())
