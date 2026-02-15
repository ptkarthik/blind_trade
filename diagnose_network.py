import requests

def diagnose():
    targets = [
        "https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
        "https://api.twelvedata.com/time_series?symbol=AAPL&interval=1min&apikey=demo",
        "https://www.google.com"
    ]
    
    for url in targets:
        print(f"\nChecking {url}...")
        try:
            res = requests.get(url, timeout=5)
            print(f"Status: {res.status_code}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    diagnose()
