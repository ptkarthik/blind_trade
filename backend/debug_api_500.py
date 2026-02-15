
import asyncio
import sys
from app.db.session import AsyncSessionLocal
from app.api.api_v1.endpoints.signals import get_todays_signals, get_sector_signals
# We need to mock the DB dependency or just call the logic directly
from app.models.job import Job
from sqlalchemy.future import select
from app.services.market_data import market_service

async def debug_500():
    print("--- Debugging /today and /sectors 500 Error ---")
    
    async with AsyncSessionLocal() as session:
        # Simulate /today
        print("\n1. Testing get_todays_signals logic...")
        try:
            query = select(Job).where(Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
            result = await session.execute(query)
            job = result.scalars().first()
            if not job:
                print("No completed job found!")
            else:
                data = job.result.get("data", [])
                print(f"Job found. Data count: {len(data)}")
                # Check for bad data
                for i, item in enumerate(data):
                    # Simulate logic that might crash
                    # e.g. accessing sector
                    s = item.get("sector")
                    c = item.get("market_cap")
                    # print(f"Item {i}: Sector={s}, Cap={c}")
        except Exception as e:
            print(f"CRASH in get_todays_signals logic: {e}")
            import traceback
            traceback.print_exc()

        # Simulate /sectors
        print("\n2. Testing get_sector_signals logic...")
        try:
            # Replicating signals.py logic
            sectors = ["Banking", "Finance", "IT", "Auto", "Pharma", "Energy", "FMCG", "Metal", "Infrastructure", "Realty", "Services"]
            response = {s: {"buys": [], "sells": [], "last_updated": "Never"} for s in sectors}
            
            data = job.result.get("data", [])
            
            for stock_data in data:
                sym = stock_data["symbol"]
                sector = stock_data.get("sector")
                
                # Logic from signals.py (potential crash point)
                if not sector or sector == "Unknown":
                    sector = market_service.SECTOR_MAP.get(sym, "Services")
                
                if sector not in response:
                    # Normalization logic
                    if sector and "Bank" in sector: sector = "Banking" # Safety check: sector could be None?
                    elif sector and "Tech" in sector: sector = "IT"
                    # ...
                
                # Check for NoneType errors if sector is None
                
        except Exception as e:
            print(f"CRASH in get_sector_signals: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_500())
