
import yfinance as yf
import pandas as pd

def debug_zomato():
    symbol = "ZOMATO.NS"
    print(f"--- FOCUSED DEBUG: {symbol} ---")
    ticker = yf.Ticker(symbol)
    
    # 1. Price check
    try:
        price = ticker.fast_info.last_price
        print(f"Price: {price}")
    except Exception as e:
        print(f"Price Check Error: {e}")

    # 2. History test - try different periods
    for p in ["1d", "5d", "1mo", "1y"]:
        try:
            hist = ticker.history(period=p)
            print(f"History ({p}): {len(hist)} rows")
            if not hist.empty:
                print(f"  Last Date: {hist.index[-1]}")
                print(f"  Last Close: {hist['Close'].iloc[-1]}")
        except Exception as e:
            print(f"History ({p}) Error: {e}")

    # 3. TwelveData check (simulated / conceptual)
    # I won't run it here to avoid key noise, but I want to see if YF is the blocker.

if __name__ == "__main__":
    debug_zomato()
