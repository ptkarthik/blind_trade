
import asyncio
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import json

async def check_jobs():
    async with AsyncSessionLocal() as session:
        query = select(Job).order_by(Job.created_at.desc()).limit(1)
        result = await session.execute(query)
        job = result.scalars().first()
        if job:
            print(f"ID: {job.id}")
            print(f"Status: {job.status}")
            res = job.result or {}
            # Exclude large signal list to see progress
            summary = {k: v for k, v in res.items() if k != "signals"}
            print(f"Result Summary: {json.dumps(summary, indent=2)}")
        else:
            print("No jobs found")

if __name__ == "__main__":
    asyncio.run(check_jobs())
