import requests

def test_local_vs_ext():
    print("Testing Local Backend (8001)...")
    try:
        res = requests.get("http://localhost:8001/", timeout=2)
        print(f"Local Success! Status: {res.status_code}")
    except Exception as e:
        print(f"Local Fail: {e}")

    print("\nTesting External (Google)...")
    try:
        res = requests.get("https://www.google.com", timeout=2)
        print(f"Ext Success! Status: {res.status_code}")
    except Exception as e:
        print(f"Ext Fail: {e}")

if __name__ == "__main__":
    test_local_vs_ext()
