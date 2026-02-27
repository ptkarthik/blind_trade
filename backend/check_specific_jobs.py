
import asyncio
import uuid
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as session:
        # These IDs came from the user's logs
        ids = [
            '6961861d-cc83-4653-9d9f-1a7054695edf', 
            'd1344a0a-9e68-4b86-b50f-514cdd3e116c'
        ]
        for jid in ids:
            try:
                # Convert string to UUID object
                u_id = uuid.UUID(jid)
                res = await session.execute(select(Job).where(Job.id == u_id))
                job = res.scalars().first()
                if job:
                    print(f"ID: {job.id} | Type: {job.type} | Created (UTC): {job.created_at} | Updated (UTC): {job.updated_at} | Status: {job.status}")
                else:
                    print(f"Job {jid} not found in database")
            except Exception as e:
                print(f"Error checking {jid}: {e}")

if __name__ == "__main__":
    asyncio.run(check())
