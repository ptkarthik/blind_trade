import sys
import os
# Ensure backend dir is in path BEFORE other imports
sys.path.append(os.getcwd())

import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.scanner_engine import scanner_engine as scanner
from app.services.intraday_engine import intraday_engine as intra_scanner

async def worker_loop():
    print(f"👷 Blind Trade Worker Started. PID: {os.getpid()}")
    
    # 0. Startup Cleanup (Reset Interrupted Jobs)
    try:
         async with AsyncSessionLocal() as session:
            # Find stuck jobs from previous crash/restart
            q = select(Job).where(Job.status == "processing")
            res = await session.execute(q)
            stuck_jobs = res.scalars().all()
            if stuck_jobs:
                print(f"⚠️ Found {len(stuck_jobs)} interrupted jobs. Marking FAILED.")
                for j in stuck_jobs:
                    j.status = "failed"
                    j.error_details = "Worker Restarted - Job Interrupted"
                await session.commit()
    except Exception as e:
        print(f"Startup Cleanup Error: {e}")

    print("👷 Worker Ready. Waiting for Jobs...")
    
    # Track running tasks
    active_tasks = set()
    MAX_CONCURRENT_JOBS = 3

    while True:
        try:
            # 0. Clean up finished tasks
            active_tasks = {t for t in active_tasks if not t.done()}
            
            # 1. Check Capacity
            if len(active_tasks) >= MAX_CONCURRENT_JOBS:
                await asyncio.sleep(2)
                continue

            async with AsyncSessionLocal() as session:
                # 2. Poll for Pending Job
                # Lock the job immediately to prevent double-fetch (Using select for update if supported, or just strict ordering)
                query = select(Job).where(Job.status == "pending").order_by(Job.created_at.asc()).limit(1)
                result = await session.execute(query)
                job = result.scalars().first()
                
                if job:
                    print(f"📦 Found Job {job.id} ({job.type}). Launching Task...")
                    
                    # 3. Mark Processing IMMEDIATELY
                    from datetime import datetime
                    job.status = "processing"
                    job.updated_at = datetime.utcnow()
                    await session.commit()
                    
                    # 4. Launch Background Task (Non-Blocking)
                    task = asyncio.create_task(process_job_task(job.id, job.type))
                    active_tasks.add(task)
                    
                    # Small sleep to ensure task starts and context switches
                    await asyncio.sleep(0.1)
                
            # Sleep before next poll if no job found
            if not job:
                await asyncio.sleep(2)
            
        except Exception as e:
            print(f"Critical Worker Loop Error: {e}")
            await asyncio.sleep(5)

async def process_job_task(job_id, job_type):
    """
    Wrapper to execute the scan and update DB status.
    Runs concurrently.
    """
    print(f"🚀 Starting Task for Job {job_id} [{job_type}]")
    try:
        if job_type == "intraday":
                data = await intra_scanner.run_scan(job_id)
        else:
                data = await scanner.run_scan(job_id, mode=job_type)
        
        # Mark Complete
        async with AsyncSessionLocal() as session:
            q = select(Job).where(Job.id == job_id)
            res = await session.execute(q)
            job = res.scalars().first()
            if job:
                from datetime import datetime
                job.status = "completed"
                job.updated_at = datetime.utcnow()
                job.result = data
                await session.commit()
                print(f"✅ Job {job_id} Completed Successfully.")

    except Exception as e:
        print(f"❌ Job {job_id} Failed: {e}")
        try:
            async with AsyncSessionLocal() as session:
                q = select(Job).where(Job.id == job_id)
                res = await session.execute(q)
                job = res.scalars().first()
                if job:
                    from datetime import datetime
                    job.status = "failed"
                    job.updated_at = datetime.utcnow()
                    job.error_details = str(e)
                    await session.commit()
        except:
             print(f"Failed to save error state for {job_id}")

if __name__ == "__main__":
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        print("Worker Stopped.")
