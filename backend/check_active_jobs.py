
import asyncio
from sqlalchemy import select, desc
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from datetime import datetime, timedelta

async def check_recent_jobs():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).order_by(desc(Job.created_at)).limit(10)
        result = await session.execute(stmt)
        jobs = result.scalars().all()
        
        print(f"{'ID':<36} | {'Status':<12} | {'Created At':<20} | {'Progress'}")
        print("-" * 80)
        for job in jobs:
            progress = "N/A"
            if job.result and isinstance(job.result, dict):
                p = job.result.get('progress', 0)
                t = job.result.get('total_steps', 0)
                progress = f"{p}/{t}"
            print(f"{str(job.id):<36} | {str(job.status):<12} | {job.created_at.strftime('%Y-%m-%d %H:%M:%S'):<20} | {progress}")

if __name__ == "__main__":
    asyncio.run(check_recent_jobs())
