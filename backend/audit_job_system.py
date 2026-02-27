
import asyncio
from sqlalchemy import select, desc
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from datetime import datetime, timedelta
import json

async def audit_job_system():
    async with AsyncSessionLocal() as session:
        print(f"--- Job System Audit at {datetime.now()} ---")
        
        # 1. Active Jobs
        stmt = select(Job).where(Job.status.in_(['processing', 'pending'])).order_by(desc(Job.updated_at))
        result = await session.execute(stmt)
        active_jobs = result.scalars().all()
        
        print(f"\nFound {len(active_jobs)} active (processing/pending) jobs:")
        print(f"{'ID':<36} | {'Type':<12} | {'Status':<12} | {'Last Updated':<25} | {'Progress'}")
        print("-" * 120)
        
        now = datetime.utcnow()
        stale_threshold = timedelta(minutes=5)
        
        for job in active_jobs:
            progress = "0/0"
            if job.result and isinstance(job.result, dict):
                p = job.result.get('progress', 0)
                t = job.result.get('total_steps', 0)
                progress = f"{p}/{t}"
            
            is_stale = (now - job.updated_at) > stale_threshold
            stale_str = "[STALE]" if is_stale else ""
            
            job_type = "UNKNOWN"
            if job.result and isinstance(job.result, dict):
                job_type = job.result.get('job_type', 'UNKNOWN')
                
            print(f"{str(job.id):<36} | {job_type:<12} | {job.status:<12} | {job.updated_at.strftime('%Y-%m-%d %H:%M:%S'):<25} | {progress} {stale_str}")

        # 2. Check for most recent 'completed' jobs
        print("\nRecently completed jobs:")
        stmt = select(Job).where(Job.status == 'completed').order_by(desc(Job.updated_at)).limit(5)
        result = await session.execute(stmt)
        completed_jobs = result.scalars().all()
        for job in completed_jobs:
             print(f"{str(job.id):<36} | {job.status:<12} | {job.updated_at.strftime('%Y-%m-%d %H:%M:%S'):<25}")

if __name__ == "__main__":
    asyncio.run(audit_job_system())
