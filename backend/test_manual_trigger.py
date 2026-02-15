
import requests
import sys

# Try both ports just in case
PORTS = [8002, 8001, 8000]

def test_manual_trigger():
    print("--- Manual Trigger Test ---")
    
    for port in PORTS:
        url = f"http://localhost:{port}/api/v1/jobs/scan"
        print(f"\nTesting {url}...")
        try:
            res = requests.post(url, json={"type": "full_scan"}, timeout=5)
            if res.status_code == 200:
                print(f"✅ Success on Port {port}!")
                print(f"Response: {res.json()}")
                return
            else:
                print(f"❌ Failed on Port {port}: {res.status_code} - {res.text}")
        except Exception as e:
            print(f"❌ Connection Error on Port {port}: {e}")

if __name__ == "__main__":
    test_manual_trigger()
