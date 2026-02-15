
import yfinance as yf

def test_daily():
    symbol = "SBIN.NS"
    print(f"Testing {symbol} Daily ...")
    t = yf.Ticker(symbol)
    df = t.history(period="1mo", interval="1d")
    print(f"Rows: {len(df)}")
    if not df.empty:
        print(df.tail(2))
    else:
        print("❌ Failed")

if __name__ == "__main__":
    test_daily()
