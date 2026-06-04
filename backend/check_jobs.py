import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        q = select(Job).where(Job.type == "intraday").order_by(Job.created_at.desc()).limit(3)
        res = await session.execute(q)
        jobs = res.scalars().all()
        for j in jobs:
            print(f"Job {j.id} | Status: {j.status} | Error: {j.error_details}")

asyncio.run(main())
