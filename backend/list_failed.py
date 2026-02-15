
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "failed").order_by(Job.updated_at.desc()).limit(20)
        res = await session.execute(stmt)
        jobs = res.scalars().all()
        print(f"FOUND {len(jobs)} FAILED JOBS")
        for j in jobs:
            print(f"ID: {j.id} | TYPE: '{j.type}' | ERR: {j.error_details}")

if __name__ == "__main__":
    asyncio.run(check())
