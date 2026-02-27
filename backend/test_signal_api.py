
import requests
import json

def test_api():
    base_url = "http://localhost:8010/api/v1/signals"
    symbols = ["ZOMATO", "ZOMATO.NS"]
    
    for sym in symbols:
        url = f"{base_url}/{sym}?mode=longterm"
        print(f"\nTesting URL: {url}")
        try:
            response = requests.get(url, timeout=30)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if "error" in data:
                    print(f"Error in response: {data['error']}")
                else:
                    print(f"Success! Symbol in result: {data.get('symbol')}")
                    # print(json.dumps(data, indent=2))
            else:
                print(f"Failed: {response.text}")
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    test_api()
