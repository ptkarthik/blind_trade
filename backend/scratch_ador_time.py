import asyncio
import sys
import os
import pandas as pd

sys.path.append(os.getcwd())
from app.services.market_data import market_service

async def main():
    print("Fetching ADOR.NS 15m data...")
    df = await market_service.get_ohlc("ADOR.NS", period="5d", interval="15m")
    
    if df is None or df.empty:
        print("Data is empty for ADOR.NS. Trying ADORWELD.NS...")
        df = await market_service.get_ohlc("ADORWELD.NS", period="5d", interval="15m")
        
    if df is None or df.empty:
        print("Still empty. Trying yfinance directly.")
        import yfinance as yf
        df = yf.download("ADORWELD.NS", period="5d", interval="15m")
    
    if df is not None and not df.empty:
        print("\n--- Last 10 Candles ---")
        # Ensure we can see the timestamps
        print(df.tail(10)[['open', 'high', 'low', 'close', 'volume']])
    else:
        print("Could not fetch data.")

if __name__ == "__main__":
    asyncio.run(main())
