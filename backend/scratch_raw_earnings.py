import asyncio
import aiohttp
from datetime import datetime, timedelta

async def fetch_earnings_date(symbol: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}?modules=calendarEvents"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3.0)) as response:
                if response.status == 200:
                    data = await response.json()
                    res = data.get("quoteSummary", {}).get("result", [])
                    if res:
                        events = res[0].get("calendarEvents", {}).get("earnings", {}).get("earningsDate", [])
                        if events:
                            # UNIX timestamp
                            ts = events[0].get("raw")
                            if ts:
                                dt = datetime.fromtimestamp(ts)
                                return dt
                return None
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

async def main():
    syms = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INVALID.NS"]
    for s in syms:
        print(f"Fetching {s}...")
        dt = await fetch_earnings_date(s)
        if dt:
            days_away = (dt - datetime.now()).days
            print(f"  {s}: Earnings on {dt.strftime('%Y-%m-%d')} ({days_away} days away)")
        else:
            print(f"  {s}: No earnings found or failed.")

if __name__ == "__main__":
    asyncio.run(main())
