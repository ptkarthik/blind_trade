
import asyncio
import logging
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job

# Suppress SQLAlchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "failed").order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        if job:
            print("=== FAILED JOB INFO ===")
            print(f"ID: {job.id}")
            print(f"TYPE: {job.type}")
            print("ERROR DETAILS:")
            print(f"[{job.error_details}]")
            print("=======================")
        else:
            print("No failed jobs found.")

if __name__ == "__main__":
    asyncio.run(check())
