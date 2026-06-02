import asyncio
import time
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job
from app.services.kite_data import kite_data

async def check_status():
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Job).where(Job.status == "in_progress").order_by(Job.created_at.desc())
        )
        jobs = res.scalars().all()
        for j in jobs:
            print(f"Job {j.id} - Status: {j.status} - Type: {j.type} - Created: {j.created_at}")
            
    print(f"\nKite Is Ready: {kite_data.is_ready}")
    try:
        if kite_data.is_ready:
            print("Testing Kite connection...")
            ltp = await asyncio.wait_for(kite_data.get_ltp(["INFY.NS"]), timeout=5.0)
            print(f"Kite LTP: {ltp}")
    except Exception as e:
        print(f"Kite Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_status())
