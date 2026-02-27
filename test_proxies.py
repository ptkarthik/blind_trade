
import asyncio
from app.services.proxy_manager import proxy_manager
import time

async def test_proxies():
    print("Testing Proxy Manager...")
    
    # 1. Refresh
    start = time.time()
    await proxy_manager._refresh_proxies()
    print(f"Refresh took {time.time() - start:.2f}s")
    
    if not proxy_manager.proxies:
        print("❌ No proxies found. Check network or sources.")
        return

    # 2. Get Proxy
    proxy = await proxy_manager.get_proxy()
    print(f"✅ Got Proxy: {proxy}")
    
    # 3. Simulate Request
    import requests
    url = "https://query1.finance.yahoo.com/v8/finance/chart/^NSEI"
    try:
        # requests.get in a non-async way for testing
        resp = requests.get(url, proxies={"http": proxy, "https": proxy}, timeout=5, verify=False)
        print(f"Request Status with Proxy: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            print(f"Fetched Nifty Price via Proxy: {price}")
    except Exception as e:
        print(f"Request failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_proxies())
