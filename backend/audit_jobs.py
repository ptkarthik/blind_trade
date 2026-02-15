
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
import json
import logging

logging.getLogger('sqlalchemy.engine').setLevel(logging.ERROR)

async def check():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.status == "failed").order_by(Job.updated_at.desc()).limit(20)
        res = await session.execute(stmt)
        jobs = res.scalars().all()
        
        output = []
        for j in jobs:
            output.append({
                "id": str(j.id),
                "type": j.type,
                "status": j.status,
                "error": j.error_details,
                "updated_at": str(j.updated_at)
            })
        
        with open("clean_failed_jobs.json", "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"DONE: Found {len(output)} failed jobs.")

if __name__ == "__main__":
    asyncio.run(check())
