
import requests
import json

def test_api_analyze():
    symbol = "CCHHL.NS"
    print(f"Testing API Analyze for {symbol}...")
    try:
        url = f"http://localhost:8012/api/v1/signals/analyze/{symbol}?mode=intraday"
        res = requests.get(url, timeout=60)
        print(f"Status Code: {res.status_code}")
        if res.status_code == 200:
            print("Response successfully received!")
            data = res.json()
            if "error" in data:
                 print(f"Error Key in Response: {data['error']}")
            else:
                 print(f"Score: {data.get('score')}")
        else:
            print(f"Error: {res.text}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    test_api_analyze()
