import sys
import os
import asyncio
import pandas as pd
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

from app.services.market_data import market_service
from app.services.ta_intraday import ta_intraday

async def test_intraday():
    print("Fetching 5m data for ZOMATO.NS...")
    df_5m = await market_service.get_ohlc("ZOMATO.NS", period="5d", interval="5m")
    
    if df_5m is None or df_5m.empty:
        print("Failed to fetch data.")
        return
        
    print(f"Data fetched: {len(df_5m)} rows")
    logic = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    df_15m = df_5m.resample('15min').agg(logic).dropna()
    
    print("\nRunning ta_intraday.analyze_stock() on 15m data...")
    res_15m = ta_intraday.analyze_stock(df_15m)
    
    print("\nResults:")
    for k, v in res_15m.items():
        if k != "groups":
            print(f"{k}: {v}")
            
    print("\nGroups details:")
    import json
    print(json.dumps(res_15m.get("groups", {}), indent=2))

if __name__ == "__main__":
    asyncio.run(test_intraday())
