import yfinance as yf
import pandas as pd

def test_pure():
    symbol = "INFY.NS"
    print(f"Testing yf.Ticker for {symbol}...")
    try:
        t = yf.Ticker(symbol)
        df = t.history(period="5d", interval="15m")
        print("Ticker History:")
        print(df.tail())
    except Exception as e:
        print(f"Ticker Failed: {e}")

    print("-" * 20)
    print(f"Testing yf.download for {symbol}...")
    try:
        df2 = yf.download(symbol, period="5d", interval="15m")
        print("Download History:")
        print(df2.tail())
    except Exception as e:
        print(f"Download Failed: {e}")

if __name__ == "__main__":
    test_pure()
