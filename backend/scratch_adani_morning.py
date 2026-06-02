import yfinance as yf
import pandas as pd
from datetime import datetime
import pytz

def check_morning_price():
    symbol = "ADANIGREEN.NS"
    print(f"Fetching today's intraday data for {symbol}...")
    
    t = yf.Ticker(symbol)
    # Fetch 1-day of 15m intervals
    df = t.history(period="1d", interval="15m")
    
    if df.empty:
        print("No data found for today.")
        return
        
    df.index = df.index.tz_convert('Asia/Kolkata')
    
    print("\nMorning Candles (IST):")
    open_price = df.iloc[0]['Open']
    
    for idx, row in df.iterrows():
        time_str = idx.strftime("%H:%M")
        close_p = row['Close']
        hike = ((close_p - open_price) / open_price) * 100
        
        print(f"[{time_str}] Close: {close_p:.2f} | % Hike from Open: {hike:.2f}%")
        
        if time_str == "09:45":
            print(f">>> At 9:45 AM, AdaniGreen was already up {hike:.2f}% from its opening price.")
            # Also calculate VWAP roughly for this window
            typical_price = (row['High'] + row['Low'] + row['Close']) / 3
            # Basic distance check
            print(f">>> Close at 9:45: {close_p:.2f}")
            break

if __name__ == "__main__":
    check_morning_price()
