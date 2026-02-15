
import yfinance as yf
import pandas as pd

def test_ohlc(symbol, period, interval):
    print(f"\nTesting {symbol} | Period: {period} | Interval: {interval}")
    try:
        t = yf.Ticker(symbol)
        df = t.history(period=period, interval=interval)
        print(f"Result: {len(df)} rows")
        if not df.empty:
            print(df.tail(2)[['Open', 'Close', 'Volume']])
        else:
            print("❌ Empty DataFrame")
    except Exception as e:
        print(f"❌ Exception: {e}")

if __name__ == "__main__":
    # Test Intraday
    test_ohlc("SBIN.NS", "1d", "15m")
    test_ohlc("SBIN.NS", "5d", "15m")
    
    # Test Daily
    test_ohlc("SBIN.NS", "1mo", "1d")
