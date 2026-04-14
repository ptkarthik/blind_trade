import asyncio
from sqlalchemy import select, desc, text
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import datetime
import uuid

async def test():
    async with AsyncSessionLocal() as session:
        # Create a mock completed job
        old_id = str(uuid.uuid4())
        old_job = Job(id=old_id, type="intraday", status="completed", result={"data": [{"symbol": "OLD"}]}, updated_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1))
        session.add(old_job)
        
        # Create a mock processing job
        new_id = str(uuid.uuid4())
        new_job = Job(id=new_id, type="intraday", status="processing", result=None, updated_at=datetime.datetime.utcnow())
        session.add(new_job)

        await session.commit()

        # RUN GET TODAYS SIGNALS LOGIC
        query = select(Job.id, Job.status, Job.type, Job.updated_at).where(
            Job.type == "intraday",
            Job.status.in_(["completed", "processing", "stopped"])
        ).order_by(
            desc(Job.status == "processing"),
            Job.result.isnot(None).desc(),
            Job.updated_at.desc()
        ).limit(5)
        
        res = await session.execute(query)
        print("\n=== RESULTS FOR TODAYS SIGNALS QUERY ===")
        for row in res.fetchall():
            print(f"ID: {row.id}, Status: {row.status}")

        # Cleanup
        await session.execute(text(f"DELETE FROM jobs WHERE id IN ('{old_id}', '{new_id}')"))
        await session.commit()

asyncio.run(test())
