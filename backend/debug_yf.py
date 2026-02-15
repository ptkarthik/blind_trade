
import yfinance as yf
import pandas as pd

def test_direct_yf():
    print("--- Direct YFinance Debug ---")
    
    # 1. Test ^NSEI
    print("\n1. Fetching ^NSEI (Nifty 50)...")
    try:
        t = yf.Ticker("^NSEI")
        df = t.history(period="5d")
        if not df.empty:
            print(f"✅ ^NSEI Success! Rows: {len(df)}")
            print(df.tail(1))
        else:
            print("❌ ^NSEI Returned Empty Data")
            # Try to see if info is available
            # print(t.info) 
    except Exception as e:
        print(f"❌ ^NSEI Error: {e}")

    # 2. Test ^NSEI.NS (Invalid check)
    print("\n2. Fetching ^NSEI.NS (Expected Fail)...")
    try:
        t = yf.Ticker("^NSEI.NS")
        df = t.history(period="5d")
        if not df.empty:
            print(f"✅ ^NSEI.NS Success?! Rows: {len(df)}")
        else:
            print("✅ ^NSEI.NS Empty (As Expected)")
    except Exception as e:
        print(f"✅ ^NSEI.NS Error: {e}")

    # 3. Test RELIANCE.NS
    print("\n3. Fetching RELIANCE.NS...")
    try:
        t = yf.Ticker("RELIANCE.NS")
        df = t.history(period="5d")
        if not df.empty:
            print(f"✅ RELIANCE.NS Success! Rows: {len(df)}")
        else:
            print("❌ RELIANCE.NS Empty")
    except Exception as e:
        print(f"❌ RELIANCE.NS Error: {e}")

if __name__ == "__main__":
    test_direct_yf()
