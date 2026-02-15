
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import logging

# Suppress all logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "failed").order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        if job:
            print("ERROR_START")
            print(job.error_details)
            print("ERROR_END")

if __name__ == "__main__":
    asyncio.run(check())
