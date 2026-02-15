
import yfinance as yf

def test(symbol):
    print(f"\n--- {symbol} ---")
    try:
        t = yf.Ticker(symbol)
        # Try different price sources
        p1 = t.fast_info.last_price
        print(f"FastInfo Price: {p1}")
        
        h = t.history(period="1d", interval="1m")
        if not h.empty:
            print(f"History Close : {h['Close'].iloc[-1]}")
            print(f"History Time  : {h.index[-1]}")
        else:
            print("History Empty")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test("RELIANCE.NS")
    test("SBIN.NS")
