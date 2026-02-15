
import asyncio
from app.db.session import AsyncSessionLocal
from app.api.api_v1.endpoints.signals import get_sector_signals
from app.db.session import get_db

async def debug_sectors():
    print("--- Debugging Sector Grouping ---")
    async with AsyncSessionLocal() as db:
        res = await get_sector_signals(mode="longterm", db=db)
        # res is a dict of sectors
        print(f"Total Sectors: {len(res)}")
        for sector, data in res.items():
            buys = data.get("buys", [])
            sells = data.get("sells", [])
            if buys or sells:
                print(f"Sector '{sector}': {len(buys)} Buys, {len(sells)} Sells")
                # Sample buy signal keys
                if buys:
                    print(f"  Sample Signal Keys: {list(buys[0].keys())}")
                    print(f"  Sample Signal: {buys[0]['symbol']} | {buys[0].get('market_cap_category')}")

if __name__ == "__main__":
    asyncio.run(debug_sectors())
