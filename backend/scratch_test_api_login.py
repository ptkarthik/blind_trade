import requests
import time

print("Sending POST request to /kite/login...")
start = time.time()
try:
    res = requests.post("http://localhost:8012/api/v1/market/kite/login", timeout=30)
    print(f"Time taken: {time.time() - start:.2f}s")
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.json()}")
except Exception as e:
    print(f"Error: {e}")
