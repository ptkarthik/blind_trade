import requests
key = "ec5ddcb7824c461b9062de08f25e0729"
url = f"https://api.twelvedata.com/price?symbol=AAPL&apikey={key}"
try:
    r = requests.get(url, timeout=10)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text}")
except Exception as e:
    print(f"Error: {e}")
