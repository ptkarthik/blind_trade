import asyncio
import logging
from sqlalchemy.orm import declarative_base

# Suppress sqlalchemy logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as session:
        query = select(Job).order_by(Job.created_at.desc()).limit(15)
        result = await session.execute(query)
        jobs = result.scalars().all()
        print("=== Recent Jobs ===")
        for j in jobs:
            print(f"ID: {j.id} | Type: {j.type} | Status: {j.status} | Created: {j.created_at}")

if __name__ == "__main__":
    asyncio.run(check())
