
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).order_by(Job.updated_at.desc()).limit(10)
        res = await session.execute(stmt)
        jobs = res.scalars().all()
        print(f"LAST 10 JOBS:")
        for j in jobs:
            progress = j.result.get('progress', 0) if j.result else 0
            total = j.result.get('total_steps', 0) if j.result else 0
            print(f"ID: {str(j.id)[:8]} | TYPE: {j.type:10} | STATUS: {j.status:10} | PROGRESS: {progress}/{total} | UPDATED: {j.updated_at}")

if __name__ == "__main__":
    asyncio.run(check())
