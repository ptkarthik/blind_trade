import sys
import os
import asyncio

sys.path.append(os.getcwd())
from app.services.market_discovery import market_discovery

async def test():
    print("Fetching market list...")
    symbols = await market_discovery.get_full_market_list()
    print(f"Got {len(symbols)} symbols")

if __name__ == "__main__":
    asyncio.run(test())
