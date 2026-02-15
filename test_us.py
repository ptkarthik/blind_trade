import yfinance as yf
import requests

def test_us():
    symbol = "AAPL"
    print(f"Testing {symbol}...")
    
    # yfinance
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="5d")
        print(f"yfinance AAPL History rows: {len(hist)}")
    except Exception as e:
        print(f"yfinance Error: {e}")

    # direct
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers)
        print(f"Direct AAPL status: {res.status_code}")
    except Exception as e:
        print(f"Direct error: {e}")

if __name__ == "__main__":
    test_us()
