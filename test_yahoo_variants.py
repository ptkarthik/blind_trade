import requests
import urllib.request
import ssl

def test_yahoo_variants():
    # Use the specific chart URL which is the data source for yfinance
    url = "https://query1.finance.yahoo.com/v8/finance/chart/ZOMATO.NS?range=1d&interval=1m"
    
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Python-urllib/3.11",
        None
    ]
    
    for agent in agents:
        print(f"\n--- Testing User-Agent: {agent} ---")
        headers = {}
        if agent:
            headers['User-Agent'] = agent
            
        try:
            print(f"Requesting {url}...")
            res = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {res.status_code}")
            if res.status_code == 200:
                print("Success! Got data.")
            else:
                print(f"Response: {res.text[:100]}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    test_yahoo_variants()
