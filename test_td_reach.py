import requests

def test_td():
    url = "https://api.twelvedata.com/price?symbol=AAPL&apikey=demo"
    print(f"Testing TwelveData (AAPL demo)...")
    try:
        res = requests.get(url, timeout=5)
        print(f"Status: {res.status_code}")
        print(f"Body: {res.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_td()
