
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
from datetime import datetime
import uuid

async def test_updates():
    print("--- Testing Rapid Progress Updates ---")
    async with AsyncSessionLocal() as session:
        # Create a test job
        job = Job(type="test", status="processing", result={"progress": 0, "total_steps": 10, "status_msg": "Test Init"})
        session.add(job)
        await session.commit()
        await session.refresh(job)
        job_id = job.id
        print(f"Created Job {job_id}")

    for i in range(1, 6):
        print(f"Update {i}...")
        try:
            async with AsyncSessionLocal() as session:
                stmt = select(Job).where(Job.id == job_id)
                res = await session.execute(stmt)
                job_obj = res.scalars().first()
                if job_obj:
                    res_dict = dict(job_obj.result or {})
                    res_dict["progress"] = i
                    res_dict["status_msg"] = f"Update {i}"
                    job_obj.result = res_dict
                    job_obj.updated_at = datetime.utcnow()
                    await session.commit()
                    print(f"✅ Update {i} committed.")
                else:
                    print("❌ Job not found.")
        except Exception as e:
            print(f"❌ Update {i} FAILED: {e}")
        await asyncio.sleep(0.5)

    print("--- Test Complete ---")

if __name__ == "__main__":
    asyncio.run(test_updates())
