
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import logging
import json

# Suppress all logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.type == "intraday", Job.status == "failed").order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        if job:
            out = {
                "id": str(job.id),
                "type": job.type,
                "error": job.error_details,
                "status": job.status
            }
            with open("err_json.txt", "w", encoding="utf-8") as f:
                f.write(json.dumps(out, indent=2))
            print("Wrote to err_json.txt")
        else:
            print("No failed jobs found.")

if __name__ == "__main__":
    asyncio.run(check())
