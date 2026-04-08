
import asyncio
import os
import sys

# Trace Path to find backend/app
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import AsyncSessionLocal
from app.api.api_v1.endpoints.papertrades import get_paper_trades

async def diag():
    print("--- 🛰️ Checking /trades API Integrity ---")
    async with AsyncSessionLocal() as db:
        try:
            res = await get_paper_trades(db=db)
            print("✅ API OK: Trades fetched successfully.")
            print(f"Data Sample: {res[:1] if res else 'Empty'}")
        except Exception as e:
            import traceback
            print(f"❌ API CRASH: {e}")
            print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(diag())
