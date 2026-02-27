
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as session:
        query = select(Job).where(Job.status.in_(["pending", "processing"]))
        result = await session.execute(query)
        jobs = result.scalars().all()
        print("\n=== Active Jobs ===")
        for j in jobs:
            print(f"ID: {j.id} | Type: {j.type} | Status: {j.status} | Updated: {j.updated_at}")
        
        if len(jobs) > 1:
            print("\n⚠️ WARNING: Multiple active jobs found. This might confuse the UI.")

if __name__ == "__main__":
    asyncio.run(check())
