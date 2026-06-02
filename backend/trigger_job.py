import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import uuid

async def main():
    async with AsyncSessionLocal() as session:
        job = Job(id=str(uuid.uuid4()), type="intraday", status="pending", trigger_source="manual")
        session.add(job)
        await session.commit()
        print(f"Created job {job.id}")

asyncio.run(main())
