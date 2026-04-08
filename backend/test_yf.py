import yfinance as yf
import pandas as pd

def test_yf():
    sym = "RELIANCE.NS"
    print(f"Testing yfinance for {sym}...")
    try:
        t = yf.Ticker(sym)
        h = t.history(period="7d", interval="15m")
        print(f"History rows: {len(h)}")
        if not h.empty:
            print(f"Columns: {h.columns.tolist()}")
            print(f"Last close: {h['Close'].iloc[-1]}")
        else:
            print("History is EMPTY")
    except Exception as e:
        print(f"Error fetching history: {e}")

    print("\nTesting batch download...")
    try:
        chunk = ["RELIANCE.NS", "TCS.NS"]
        data = yf.download(chunk, period="7d", interval="15m", group_by='ticker')
        print(f"Batch rows: {len(data)}")
        if not data.empty:
            print(f"Index: {data.index[0]} to {data.index[-1]}")
        else:
            print("Batch is EMPTY")
    except Exception as e:
        print(f"Batch error: {e}")

if __name__ == "__main__":
    test_yf()
