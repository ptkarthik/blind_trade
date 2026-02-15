
import asyncio
import json
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as session:
        # Get the CURRENT processing full_scan
        stmt = select(Job).where(Job.type == "full_scan", Job.status == "processing").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
        if not job:
            print("No processing full_scan found.")
            return

        print(f"Inspecting Current Job: {job.id}, Progress: {job.result.get('progress')}/{job.result.get('total_steps')}")
        data = job.result.get("data", [])
        
        if not data:
            print("No data items in job result yet.")
            return

        # Show first 5 items
        for item in data[:5]:
            print(f"\n--- {item['symbol']} ---")
            print(f"LTP: {item['price']}, Smart Entry: {item['entry']}")
            print(f"Strategic Summary: {item.get('strategic_summary', 'N/A')}")

if __name__ == "__main__":
    asyncio.run(inspect())
