import asyncio
from app.services.market_data import market_service
import pandas as pd

async def check_data_length():
    print("Testing data fetch for RELIANCE.NS...")
    # This uses the current proxy config with SSL-verify=False
    res = await market_service.get_batch_ohlc(["RELIANCE.NS"], period="7d", interval="15m")
    
    if "RELIANCE.NS" in res:
        df = res["RELIANCE.NS"]
        print(f"Success! Fetched {len(df)} candles.")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Last Index: {df.index[-1]}")
        if len(df) < 40:
            print("WARNING: Data length is BELOW the 40-candle threshold used in intraday_engine!")
    else:
        print("FAILED: No data returned even with proxies.")

if __name__ == "__main__":
    asyncio.run(check_data_length())
