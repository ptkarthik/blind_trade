import requests
from curl_cffi import requests as curl_requests
import yfinance as yf

def test_all():
    url = "https://query1.finance.yahoo.com/v8/finance/chart/RELIANCE.NS?range=1d&interval=15m"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    print("Testing standard requests...")
    try:
        r1 = requests.get(url, headers=headers, timeout=5)
        print("Standard requests status:", r1.status_code)
    except Exception as e:
        print("Standard requests failed:", e)
        
    print("\nTesting curl_cffi...")
    try:
        r2 = curl_requests.get(url, impersonate="chrome120", timeout=5)
        print("curl_cffi status:", r2.status_code)
    except Exception as e:
        print("curl_cffi failed:", e)
        
    print("\nTesting yfinance...")
    try:
        t = yf.Ticker("RELIANCE.NS")
        df = t.history(period="1d", interval="15m")
        print("yfinance df len:", len(df))
    except Exception as e:
        print("yfinance failed:", e)

if __name__ == "__main__":
    test_all()
