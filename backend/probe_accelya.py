import yfinance as yf
import pandas as pd

def test_accelya():
    symbol = "ACCELYA.NS"
    print(f"Testing {symbol}...")
    try:
        # Test 15m 1mo fetch
        t = yf.Ticker(symbol)
        df = t.history(period="1mo", interval="15m")
        print(f"15m Data points: {len(df)}")
        if not df.empty:
            daily_vols = df['Volume'].resample('1D').sum()
            daily_vols = daily_vols[daily_vols > 0].tail(20)
            adv20 = daily_vols.mean()
            print(f"Calculated ADV20: {adv20}")
        else:
            print("15m Data is empty!")
            
        # Test 1d fetch as fallback
        df_1d = t.history(period="1mo", interval="1d")
        print(f"1d Data points: {len(df_1d)}")
        if not df_1d.empty:
            adv20_1d = df_1d['Volume'].tail(20).mean()
            print(f"Calculated ADV20 (from 1d): {adv20_1d}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_accelya()
