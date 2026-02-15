import requests
import urllib.request
import ssl

def test_ip():
    url = "https://api.ipify.org?format=json"
    print(f"Testing reachability to {url}...")
    
    # 1. Requests
    print("\n--- Method: Requests ---")
    try:
        res = requests.get(url, timeout=5)
        print(f"Status: {res.status_code}, Body: {res.text}")
    except Exception as e:
        print(f"Requests Error: {e}")

    # 2. Urllib
    print("\n--- Method: Urllib ---")
    try:
        # Avoid SSL certificate verify for testing
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(url, timeout=5, context=ctx) as response:
            print(f"Status: {response.status}, Body: {response.read().decode()}")
    except Exception as e:
        print(f"Urllib Error: {e}")

if __name__ == "__main__":
    test_ip()
