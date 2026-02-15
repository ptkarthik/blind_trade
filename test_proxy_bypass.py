import requests
import os

def test_no_proxy():
    # Force NO proxy for this session
    os.environ['HTTP_PROXY'] = ""
    os.environ['HTTPS_PROXY'] = ""
    os.environ['no_proxy'] = "*"
    
    url = "https://www.google.com"
    print(f"Testing reachability to {url} WITH PROXY BYPASS...")
    
    try:
        # Explicitly disable proxies in the request too
        res = requests.get(url, timeout=5, proxies={"http": None, "https": None})
        print(f"Status: {res.status_code}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_no_proxy()
