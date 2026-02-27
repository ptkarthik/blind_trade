
import yfinance as yf
import pandas as pd

def test_download():
    print("Testing yf.download for ZOMATO.NS (15m, 5d)...")
    try:
        df = yf.download(tickers="ZOMATO.NS", period="5d", interval="15m", progress=False)
        print(f"Result: {len(df)} rows")
        if not df.empty:
            print(df.tail())
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_download()
