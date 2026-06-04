import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        q = select(Job).where(Job.status == "processing", Job.type == "intraday")
        res = await session.execute(q)
        jobs = res.scalars().all()
        for j in jobs:
            j.status = "failed"
            j.error_details = "Reset stuck job"
        await session.commit()
        print(f"Reset {len(jobs)} stuck intraday jobs.")

asyncio.run(main())
