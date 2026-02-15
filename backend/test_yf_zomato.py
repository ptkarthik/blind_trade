
import yfinance as yf
import json

def test_yf():
    symbol = "ZOMATO.NS"
    print(f"Testing {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # Fast info
    try:
        info = ticker.fast_info
        print(f"✅ Fast Info Success")
        print(f"   Price: {info.get('last_price')}")
        print(f"   Cap: {info.get('market_cap')}")
    except Exception as e:
        print(f"❌ Fast Info Error: {e}")
        
    # Full info (slow)
    try:
        print(f"Fetching full info...")
        full_info = ticker.info
        print(f"✅ Full Info Success")
        print(f"   Sector: {full_info.get('sector')}")
        print(f"   Long Name: {full_info.get('longName')}")
    except Exception as e:
        print(f"❌ Full Info Error: {e}")

    # History
    try:
        hist = ticker.history(period="1mo")
        print(f"✅ History Rows: {len(hist)}")
    except Exception as e:
        print(f"❌ History Error: {e}")

if __name__ == "__main__":
    test_yf()
