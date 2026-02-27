import asyncio
from app.services.ta_intraday import ta_intraday
from app.services.market_data import market_service
import pandas as pd

async def test_penny():
    df = await market_service.get_ohlc("MTEDUCARE.NS", period="5d", interval="15m")
    if df is not None and not df.empty:
        res = ta_intraday.analyze_stock(df)
        print("--- MTEDUCARE Risk Test ---")
        print(f"Price: {df['close'].iloc[-1]}")
        print(f"Signal Trend: {res['trend']}")
        print(f"Target: {res['resistance']}")
        print(f"Stop Loss: {res['support']}")
        print(f"Target Reason: {res['target_reason']}")
        print("---------------------------")
    else:
        print("Failed to fetch data.")

asyncio.run(test_penny())
