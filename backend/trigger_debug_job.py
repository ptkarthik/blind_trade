
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from datetime import datetime
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def f():
    async with AsyncSessionLocal() as s:
        new_job = Job(
            type="intraday",
            status="pending",
            error_details="DEBUG_SLOT_TARGETED_TEST"
        )
        s.add(new_job)
        await s.commit()
        await s.refresh(new_job)
        print(f"Triggered Debug Job: {new_job.id}")

if __name__ == "__main__":
    asyncio.run(f())
