import asyncio
import sys
import os
import logging
sys.path.append(os.getcwd())
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from sqlalchemy.orm import defer

async def check_performance():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Job)
            .options(defer(Job.result))
            .where(Job.type == "intraday")
            .where(Job.status == "completed")
            .order_by(Job.updated_at.desc())
            .limit(1)
        )
        job = result.scalars().first()
        if not job:
            print("❌ No completed intraday jobs found.")
            return

        duration = job.updated_at - job.created_at
        print(f"\n📊 --- [V11 PULSE PERFORMANCE] ---")
        print(f"🚀 TOTAL RUN TIME: {duration}")
        print(f"🔹 Started:   {job.created_at}")
        print(f"🔹 Completed: {job.updated_at}")
        print(f"----------------------------------\n")

if __name__ == "__main__":
    asyncio.run(check_performance())
