import asyncio
import time
from curl_cffi import requests

async def speed_test():
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS", "ICICIBANK.NS"]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    }
    
    print(f"🚀 [SPEED TEST] Attempting to fetch {len(symbols)} symbols sequentially...")
    
    start_time = time.time()
    for sym in symbols:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=15m&range=7d"
        try:
            r = requests.get(url, headers=headers, impersonate="chrome120")
            if r.status_code == 200:
                print(f"✅ {sym}: Fetched successfully.")
            else:
                print(f"❌ {sym}: Failed with status {r.status_code}")
        except Exception as e:
            print(f"❌ {sym}: Error: {str(e)}")
            
    end_time = time.time()
    total_time = end_time - start_time
    print(f"\n⏱️ Finished in {total_time:.2f} seconds.")
    print(f"⚡ Throughput: {len(symbols)/total_time:.2f} symbols/sec")

if __name__ == "__main__":
    asyncio.run(speed_test())
