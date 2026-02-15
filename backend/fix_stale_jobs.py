
import asyncio
import sys
import os
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.job import Job

# Ensure backend dir is in path
sys.path.append(os.getcwd())

async def fix_stale_jobs():
    print("🔧 Checking for stale 'processing' jobs...")
    async with AsyncSessionLocal() as session:
        # Find stuck jobs
        query = select(Job).where(Job.status == "processing")
        result = await session.execute(query)
        stuck_jobs = result.scalars().all()
        
        if not stuck_jobs:
            print("✅ No stuck jobs found. System is clean.")
            return

        for job in stuck_jobs:
            print(f"⚠️ Found Stale Job {job.id} (Status: {job.status}). Marking as FAILED.")
            job.status = "failed"
            job.error_details = "System Restarted / Stale Job Cleanup"
            
        await session.commit()
        print(f"✅ Fixed {len(stuck_jobs)} stuck jobs. You can now start a new scan.")

if __name__ == "__main__":
    asyncio.run(fix_stale_jobs())
