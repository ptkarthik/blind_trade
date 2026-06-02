import asyncio
import pandas as pd
import yfinance as yf
from app.services.ta_swing import ta_swing
from app.services.market_data import market_service

async def test_yesterday():
    print("Fetching data for SUPRIYA.NS up to yesterday...")
    # Fetch 1 year of data
    df = yf.Ticker("SUPRIYA.NS").history(period="1y", interval="1d")
    df.columns = [c.lower() for c in df.columns]
    
    # Remove today's candle to simulate "yesterday"
    # Today is May 29. Yesterday was May 28.
    df = df[df.index < '2026-05-29']
    
    print(f"Data ends at: {df.index[-1]}")
    
    nifty_20d_ret = -1.0 # Assume slightly bearish Nifty for yesterday
    
    ctx = ta_swing.compute_context(df)
    
    print("\n--- Technical Context ---")
    print(f"Close: {df['close'].iloc[-1]}")
    print(f"RSI: {ctx['rsi']}")
    print(f"SMA 20: {ctx['sma_20']}")
    print(f"SMA 50: {ctx['sma_50']}")
    print(f"Trend 1D: {ctx['trend_1d']}")
    print(f"Volume Ratio: {ctx['vol_ratio']}")
    
    pb = ta_swing.analyze_pullback(df, nifty_20d_ret, ctx, False)
    bo = ta_swing.analyze_breakout(df, nifty_20d_ret, ctx, False)
    
    print("\n--- Pullback Analysis ---")
    print(f"Match: {pb.get('match')}")
    print(f"Reason: {pb.get('reason')}")
    
    print("\n--- Breakout Analysis ---")
    print(f"Match: {bo.get('match')}")
    print(f"Reason: {bo.get('reason')}")

if __name__ == "__main__":
    asyncio.run(test_yesterday())
