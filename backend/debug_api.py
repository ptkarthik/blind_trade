import requests
import json
import time

BASE_URL = "http://localhost:8000/api/v1"

def check_endpoint(endpoint):
    print(f"Checking {endpoint}...")
    start = time.time()
    try:
        response = requests.get(f"{BASE_URL}{endpoint}", timeout=10)
        duration = time.time() - start
        print(f"Status: {response.status_code}")
        print(f"Time: {duration:.2f}s")
        try:
            print("Response:", json.dumps(response.json(), indent=2))
        except:
            print("Response Text:", response.text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_endpoint("/market/status")
    print("-" * 50)
    check_endpoint("/signals/today")
