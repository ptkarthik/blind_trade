import asyncio
import sys
import os
import logging
sys.path.append(os.getcwd())
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Job)
            .where(Job.type == "intraday")
            .where(Job.status == "processing")
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        job = result.scalars().first()
        if not job:
            print("🛑 NO LIVE SCAN FOUND (Status: processing).")
            return

        data = job.result.get("data", [])
        print(f"\n🛰️ --- [LIVE SCAN INSPECTION] ---")
        print(f"🔹 Job ID:    {job.id}")
        print(f"🔹 Progress:  {job.result.get('progress', 0)} / {job.result.get('total_steps', 0)}")
        print(f"🔹 Data Count: {len(data)}")
        
        if data:
            print(f"\n📊 --- [TOP 5 SCORES FOUND] ---")
            for i, s in enumerate(data[:5]):
                print(f"{i+1}. {s.get('symbol')} | Score: {s.get('score')} | Signal: {s.get('signal')} | Label: {s.get('signal_label')}")
        else:
            print("⚠️ No scorable data in job result yet.")
        print(f"----------------------------------\n")

if __name__ == "__main__":
    asyncio.run(inspect())
