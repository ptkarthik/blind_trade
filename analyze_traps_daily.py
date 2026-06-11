import yfinance as yf
from datetime import date
import sys

symbols = ['ABSLAMC.NS', 'CARYSIL.NS', 'HGS.NS', '^NSEI']
today = date.today().isoformat()

for sym in symbols:
    try:
        ticker = yf.Ticker(sym)
        df = ticker.history(period="1d")
        if df.empty:
            print(f"[{sym}] No data")
            continue
            
        row = df.iloc[-1]
        open_p = row['Open']
        high_p = row['High']
        low_p = row['Low']
        close_p = row['Close']
        
        print(f"[{sym}] Open: {open_p:.2f} | High: {high_p:.2f} | Low: {low_p:.2f} | Close: {close_p:.2f}")
    except Exception as e:
        print(f"[{sym}] Error: {e}")
