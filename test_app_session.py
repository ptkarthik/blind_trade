import yfinance as yf
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import pandas as pd
import numpy as np

def test_app_logic():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.5',
        'Origin': 'https://finance.yahoo.com',
        'Referer': 'https://finance.yahoo.com/'
    })

    symbol = "ZOMATO.NS"
    print(f"Testing {symbol} with App Session...")
    
    try:
        print("\n--- Testing Google reachability ---")
        g_res = session.get("https://www.google.com", timeout=5)
        print(f"Google Status: {g_res.status_code}")
        
        ticker = yf.Ticker(symbol, session=session)
        print("\n--- Fast Info ---")
        info = {
            "price": ticker.fast_info.last_price,
            "prev_close": ticker.fast_info.previous_close,
            "mc": ticker.fast_info.market_cap
        }
        print(info)
        
        print("\n--- History (5d) ---")
        hist = ticker.history(period="5d")
        print(f"Rows: {len(hist)}")
        if not hist.empty:
            print(hist.tail(1))
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_app_logic()
