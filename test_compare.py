import yfinance as yf
import pandas as pd

def test():
    symbols = ["RELIANCE.NS", "ZOMATO.NS"]
    for symbol in symbols:
        print(f"\n--- Testing {symbol} ---")
        ticker = yf.Ticker(symbol)
        
        hist = ticker.history(period="5d")
        print(f"History rows: {len(hist)}")
        if not hist.empty:
            print(hist.tail(1))
        
        try:
            price = ticker.fast_info.last_price
            print(f"Fast Info Price: {price}")
        except Exception as e:
            print(f"Fast Info Error: {e}")

if __name__ == "__main__":
    test()
