import yfinance as yf
import requests
import asyncio
from app.services.proxy_manager import proxy_manager
import pandas as pd
import warnings

# Disable SSL warnings
warnings.filterwarnings('ignore')

async def debug_proxy_yf():
    print("--- Probing Proxy Health ---")
    proxy = await proxy_manager.get_proxy()
    print(f"Using Proxy: {proxy}")
    
    if not proxy:
        print("CRITICAL: No proxies found in ProxyManager!")
        return

    # 1. Test basic connectivity via requests
    try:
        print(f"Testing connectivity to google.com via {proxy}...")
        r = requests.get("https://www.google.com", proxies={"https": proxy}, timeout=10, verify=False)
        print(f"Requests Success! Status: {r.status_code}")
    except Exception as e:
        print(f"Requests Failed via proxy: {e}")

    # 2. Test yfinance via proxy
    try:
        print(f"Testing yfinance (RELIANCE.NS) via {proxy}...")
        ticker = yf.Ticker("RELIANCE.NS")
        # We try to use a session to bypass SSL
        session = requests.Session()
        session.verify = False
        session.proxies = {"https": proxy}
        
        df = ticker.history(period="1d", interval="15m", proxy=proxy)
        print(f"YFinance Rows: {len(df)}")
        if not df.empty:
            print(f"Last Price: {df['Close'].iloc[-1]}")
        else:
            print("YFinance returned EMPTY DataFrame.")
    except Exception as e:
        print(f"YFinance Crash: {e}")

if __name__ == "__main__":
    asyncio.run(debug_proxy_yf())
