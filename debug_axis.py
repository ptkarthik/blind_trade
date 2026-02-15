
import asyncio
from app.services.market_data import market_service
from app.services.ta import ta_engine
import pandas as pd

async def debug_axis():
    symbol = "AXISBANK"
    print(f"--- Debugging {symbol} Analysis ---")
    
    # Fetch Data
    df = await market_service.get_ohlc(symbol, period="5d", interval="15m")
    if df.empty:
        print("❌ No Data Found")
        return

    # Analyze
    analysis = ta_engine.analyze_stock(df, mode="intraday")
    
    print(f"\nPrice: {analysis['close']}")
    print(f"Score: {analysis['score']}")
    print("\n--- Reasons ---")
    for r in analysis['reasons']:
        print(r)
        
    print("\n--- Indicators ---")
    print(f"RSI: {analysis['rsi']}")
    print(f"EMA 20: {analysis['ema_20']}")
    print(f"Trend: {analysis['trend']}")

if __name__ == "__main__":
    asyncio.run(debug_axis())
