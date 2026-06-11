import yfinance as yf
import pandas as pd
from datetime import date

symbols = ['ABSLAMC.NS', 'CARYSIL.NS', 'HGS.NS', '^NSEI']
today = date.today().isoformat()

print(f"--- INTRADAY ANALYSIS FOR {today} ---")

for sym in symbols:
    try:
        ticker = yf.Ticker(sym)
        df = ticker.history(period="1d", interval="15m")
        if df.empty:
            print(f"\n[{sym}]: No intraday data available.")
            continue
            
        open_price = df['Open'].iloc[0]
        high_price = df['High'].max()
        low_price = df['Low'].min()
        close_price = df['Close'].iloc[-1]
        
        # Calculate drop from the absolute high of the day
        drop_from_high = ((close_price - high_price) / high_price) * 100
        change_from_open = ((close_price - open_price) / open_price) * 100
        
        print(f"\n[{sym}]")
        print(f"  Open: {open_price:.2f} | High: {high_price:.2f} | Low: {low_price:.2f} | Close: {close_price:.2f}")
        print(f"  Change from Open: {change_from_open:.2f}%")
        print(f"  Drop from High: {drop_from_high:.2f}%")
        
        # Analyze the shape of the day
        if open_price == high_price:
            print("  Pattern: Open=High (Immediate aggressive selling from the bell)")
        elif high_price > open_price and drop_from_high < -2:
            print("  Pattern: Morning Fakeout / Bull Trap (Pushed up then dumped aggressively)")
        elif change_from_open < -3:
            print("  Pattern: Heavy Intraday Bleed (Consistent selling pressure all day)")
        else:
            print("  Pattern: General drift/pullback")
            
    except Exception as e:
        print(f"Failed for {sym}: {e}")
