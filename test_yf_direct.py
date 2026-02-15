import requests
import json

def test_direct_yf():
    symbol = "ZOMATO.NS"
    print(f"Testing direct YF query for {symbol}...")
    
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        data = response.json()
        
        if data['chart']['result']:
            result = data['chart']['result'][0]
            print("Successfully fetched data!")
            print(f"Close prices count: {len(result['indicators']['quote'][0]['close'])}")
        else:
            print(f"Error in response: {data['chart']['error']}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_direct_yf()
