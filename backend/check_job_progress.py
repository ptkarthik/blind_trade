
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
import json

async def check_job_progress():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "processing").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
        if not job:
            # Check latest completed if no processing
            stmt = select(Job).order_by(Job.created_at.desc()).limit(1)
            res = await session.execute(stmt)
            job = res.scalars().first()
            print("No active 'processing' job. Checking latest job:")
        else:
            print("Active 'processing' job found:")

        if job:
            print(f"ID: {job.id}")
            print(f"Status: {job.status}")
            print(f"Result JSON: {json.dumps(job.result, indent=2)}")
        else:
            print("No jobs found in DB.")

if __name__ == "__main__":
    asyncio.run(check_job_progress())
