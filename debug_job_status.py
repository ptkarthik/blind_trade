import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
import json

async def check_jobs():
    async with AsyncSessionLocal() as session:
        # Get latest intraday job
        stmt = select(Job).where(Job.type == "intraday").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
    with open("debug_output.txt", "w") as f:
        if job:
            f.write(f"Job ID: {job.id}\n")
            f.write(f"Status: {job.status}\n")
            f.write(f"Created: {job.created_at}\n")
            f.write(f"Updated: {job.updated_at}\n")
            
            if job.result:
                f.write(f"Progress: {job.result.get('progress')} / {job.result.get('total_steps')}\n")
                data = job.result.get('data', [])
                f.write(f"Signals Found: {len(data)}\n")
                if len(data) > 0:
                    f.write(f"Sample Signal: {data[0]['symbol']} {data[0]['score']}\n")
            else:
                f.write("No result data yet.\n")
        else:
            f.write("No intraday jobs found.\n")

if __name__ == "__main__":
    asyncio.run(check_jobs())
