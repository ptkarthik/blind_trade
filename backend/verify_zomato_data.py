
import asyncio
import pandas as pd
import yfinance as yf
import time
import random
from typing import Dict, Any

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"
]

async def test_component(name, coro):
    print(f"Testing {name}...")
    start = time.time()
    try:
        res = await asyncio.wait_for(coro, timeout=20)
        end = time.time()
        print(f"  ✅ {name} Success ({end-start:.2f}s)")
        if isinstance(res, pd.DataFrame):
            print(f"     Rows: {len(res)}")
        elif isinstance(res, dict):
            print(f"     Keys: {list(res.keys())[:5]}")
        return True
    except asyncio.TimeoutError:
        print(f"  ❌ {name} TIMEOUT (20s)")
    except Exception as e:
        print(f"  ❌ {name} FAILED: {e}")
    return False

async def run_diagnostics(symbol="ZOMATO.NS"):
    print(f"Starting diagnostics for {symbol}...")
    import requests
    session = requests.Session()
    session.headers.update({'User-Agent': random.choice(user_agents)})
    ticker = yf.Ticker(symbol, session=session)

    # 1. Price
    async def get_price():
        return ticker.fast_info.last_price
    await test_component("Fast Info Price", get_price())

    # 2. History
    async def get_hist():
        return ticker.history(period="1mo", interval="1d")
    await test_component("History (1mo/1d)", get_hist())

    # 3. Info (The likely culprit)
    async def get_info():
        return ticker.info
    await test_component("Ticker Info", get_info())

    # 4. Financials
    async def get_fin():
        return ticker.financials
    await test_component("Financials", get_fin())

if __name__ == "__main__":
    asyncio.run(run_diagnostics())
