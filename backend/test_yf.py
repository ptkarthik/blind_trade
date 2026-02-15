import yfinance as yf
import time

def test_fetch(symbol):
    print(f"Fetching {symbol}...")
    start = time.time()
    try:
        ticker = yf.Ticker(symbol)
        price = ticker.fast_info.last_price
        print(f"Success! {symbol} Price: {price}")
    except Exception as e:
        print(f"Failed {symbol}: {e}")
    print(f"Time taken: {time.time() - start:.2f}s")

if __name__ == "__main__":
    test_fetch("^NSEI") # Nifty 50
    test_fetch("RELIANCE.NS")
