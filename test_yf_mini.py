import yfinance as yf
import pandas as pd

def test():
    symbol = "ZOMATO.NS"
    print(f"Testing {symbol}...")
    ticker = yf.Ticker(symbol)
    
    print("\n--- History (1mo) ---")
    hist = ticker.history(period="1mo")
    print(hist)
    
    print("\n--- Info ---")
    try:
        print(ticker.info)
    except Exception as e:
        print(f"Info Error: {e}")

    print("\n--- Fast Info ---")
    try:
        print(f"Price: {ticker.fast_info.last_price}")
    except Exception as e:
        print(f"Fast Info Error: {e}")

if __name__ == "__main__":
    test()
