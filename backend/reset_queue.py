
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import update
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def f():
    async with AsyncSessionLocal() as s:
        q = update(Job).where(Job.status.in_(['pending', 'processing'])).values(status='failed', error_details='Manual Reset')
        await s.execute(q)
        await s.commit()
        print('Queue Reset')

if __name__ == "__main__":
    asyncio.run(f())
