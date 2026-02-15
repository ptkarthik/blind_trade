
import asyncio
from app.services.market_data import market_service
from app.services.ta import ta_engine
import pandas as pd

async def test_sector_fetch():
    await market_service.initialize()
    
    # Pick a sector
    sector = "Banking"
    symbols = market_service.get_stocks_by_sector(sector)
    print(f"Testing Sector: {sector} ({len(symbols)} stocks)")
    
    for sym in symbols[:5]: # Test top 5
        print(f"\n--- Analyzing {sym} ---")
        try:
            # mimic signals.py logic
            df = await market_service.get_ohlc(sym, period="5d", interval="15m")
            print(f"OHLC Rows: {len(df)}")
            if not df.empty:
                print(f"Last Candle: {df.index[-1]}")
                print(df.tail(2))
                
                analysis = ta_engine.analyze_stock(df, mode="intraday")
                if analysis:
                    print(f"✅ Analysis Score: {analysis.get('score')}")
                else:
                    print(f"❌ Analysis Failed (Usually < 50 candles)")
            else:
                print("❌ OHLC Empty")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_sector_fetch())
