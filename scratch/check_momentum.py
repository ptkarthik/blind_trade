import yfinance as yf
import pandas as pd
from datetime import datetime

def check_stock_history(symbol):
    print(f"--- Technical Audit: {symbol} ---")
    ticker = yf.Ticker(symbol)
    
    # Get 15m data for the last 2 days
    df = ticker.history(period="2d", interval="15m")
    if df.empty:
        print("No data found.")
        return
    
    print(f"Latest Timestamp in Data: {df.index[-1]}")
    print(f"Latest Close Price: {df['Close'].iloc[-1]:.2f}")
    
    # Calculate RVOL (Volume vs 20-period avg)
    avg_vol = df['Volume'].rolling(20).mean().iloc[-1]
    last_vol = df['Volume'].iloc[-1]
    rvol = last_vol / avg_vol if avg_vol > 0 else 0
    
    print(f"Relative Volume (RVOL): {rvol:.2f}")
    
    # Check closing session (last 4 candles)
    last_day = df.index[-1].date()
    yesterday_data = df[df.index.date == last_day]
    print(f"Yesterday's Move: {((yesterday_data['Close'].iloc[-1] - yesterday_data['Open'].iloc[0]) / yesterday_data['Open'].iloc[0] * 100):.2f}%")
    print("Final 4 Candles (15m each):")
    print(yesterday_data.tail(4)[['Open', 'High', 'Low', 'Close', 'Volume']])

if __name__ == "__main__":
    check_stock_history("EBGNG.NS")
    print("\n")
    check_stock_history("CRISIL.NS")
