
import yfinance as yf
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd

def test_yf_direct():
    symbol = "RELIANCE.NS"
    print(f"Testing YF Direct for {symbol} (15m, 5d)...")

    session = requests.Session()
    session.trust_env = False
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })

    ticker = yf.Ticker(symbol, session=session)
    
    try:
        # Try without proxy first
        hist = ticker.history(period="5d", interval="15m")
        print("Fetch Result:")
        print(hist)
        if hist.empty:
            print("❌ Empty DataFrame returned by yfinance")
            # Print shared info to see if ticker is valid
            # print(ticker.fast_info) 
    except Exception as e:
        print(f"❌ YF Exception: {e}")

if __name__ == "__main__":
    test_yf_direct()
