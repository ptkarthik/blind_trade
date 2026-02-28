import sys
import os
import socket
# Ensure backend dir is in path BEFORE other imports
sys.path.append(os.getcwd())

# Prevent thread pool exhaustion from rogue hanging network requests
socket.setdefaulttimeout(15.0)

import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.scanner_engine import longterm_scanner_engine as longterm_scanner
from app.services.intraday_engine import intraday_engine as intra_scanner
from app.services.swing_engine import swing_engine as swing_scanner

# Worker Mode Configuration
WORKER_TYPE = os.getenv("WORKER_TYPE", "all").lower()
AUTO_SCHEDULE = os.getenv("AUTO_SCHEDULE", "false").lower() == "true"
WORKER_ID = os.getenv("WORKER_ID", hex(os.getpid())[2:])

if WORKER_TYPE == "longterm":
    ALLOWED_JOB_TYPES = ["full_scan", "sector_scan"]
elif WORKER_TYPE == "intraday":
    ALLOWED_JOB_TYPES = ["intraday"]
elif WORKER_TYPE == "swing":
    ALLOWED_JOB_TYPES = ["swing_scan"]
else:
    ALLOWED_JOB_TYPES = ["full_scan", "sector_scan", "intraday", "swing_scan"]

def log(msg):
    from datetime import datetime
    color_prefix = ""
    # Add simple visual distinction for different worker types
    if WORKER_TYPE == "longterm": color_prefix = "[LONG]"
    elif WORKER_TYPE == "intraday": color_prefix = "[INT]"
    elif WORKER_TYPE == "swing": color_prefix = "[SWING]"
    else: color_prefix = "[ALL]"
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {color_prefix} [ID-{WORKER_ID}] {msg}", flush=True)

log("="*60)
log(f"🛠️  Worker Initialized")
log(f"Handling: {', '.join(ALLOWED_JOB_TYPES)}")
log(f"Auto-Schedule: {'ENABLED' if AUTO_SCHEDULE else 'DISABLED'}")
log("="*60)

async def manage_recurring_scans():
    """
    Checks if 10 minutes have passed since the last scan of each type 
    and triggers a new one if needed.
    """
    from datetime import datetime, timedelta
    RECURRENCE_INTERVAL = timedelta(minutes=10)
    
    # Only check types this worker is responsible for
    types_to_check = [t for t in ["full_scan", "intraday", "swing_scan"] if t in ALLOWED_JOB_TYPES]
    
    if not types_to_check:
        return
    
    async with AsyncSessionLocal() as session:
        for job_type in types_to_check:
            # 1. Check if any job of this type is already pending or processing
            active_query = select(Job).where(Job.type == job_type, Job.status.in_(["pending", "processing"]))
            active_res = await session.execute(active_query)
            if active_res.scalars().first():
                continue # Already busy
            
            # 2. Get the latest completed/failed job of this type
            history_query = select(Job).where(Job.type == job_type).order_by(Job.created_at.desc()).limit(1)
            history_res = await session.execute(history_query)
            last_job = history_res.scalars().first()
            
            should_trigger = False
            if not last_job:
                should_trigger = True # Never run before
            else:
                elapsed = datetime.utcnow() - last_job.updated_at
                if elapsed >= RECURRENCE_INTERVAL:
                    should_trigger = True
            
            if should_trigger:
                log(f"⏰ [SCHEDULER] Auto-triggering {job_type} (10min interval reached)")
                new_job = Job(type=job_type, status="pending")
                session.add(new_job)
                await session.commit()

async def worker_loop():
    log(f"👷 Worker Process Started. PID: {os.getpid()}")
    
    # 0. Startup Cleanup (Reset Interrupted Jobs)
    try:
        async with AsyncSessionLocal() as session:
            # CLEAN SLATE: Only cleanup jobs this worker is responsible for
            # Flush BOTH 'pending' and 'processing' to ensure no ghost jobs start.
            q = select(Job).where(
                Job.status.in_(["processing", "pending"]), 
                Job.type.in_(ALLOWED_JOB_TYPES)
            )
            res = await session.execute(q)
            stuck_jobs = res.scalars().all()
            if stuck_jobs:
                log(f"⚠️ Flushing {len(stuck_jobs)} legacy {WORKER_TYPE} jobs (Pending/Processing).")
                for j in stuck_jobs:
                    j.status = "failed"
                    j.error_details = f"Worker Started - Queue Flushed for {WORKER_TYPE}"
                await session.commit()
    except Exception as e:
        log(f"Startup Cleanup Error: {e}")

    log("👷 Worker Ready. Waiting for Jobs...")
    
    # Track running tasks
    active_tasks = set()
    MAX_CONCURRENT_JOBS = 3

    while True:
        try:
            # 0. Manage Recurring Scans (Check every loop iteration, manage_recurring_scans handles timing)
            if AUTO_SCHEDULE:
                await manage_recurring_scans()

            # 1. Clean up finished tasks
            active_tasks = {t for t in active_tasks if not t.done()}
            
            # 2. Check Capacity
            if len(active_tasks) >= MAX_CONCURRENT_JOBS:
                await asyncio.sleep(2)
                continue
            async with AsyncSessionLocal() as session:
                # 2. Poll for Pending Job relevant to this worker
                query = select(Job).where(
                    Job.status == "pending",
                    Job.type.in_(ALLOWED_JOB_TYPES)
                ).order_by(Job.created_at.asc()).limit(1)
                result = await session.execute(query)
                job = result.scalars().first()
                
                if job:
                    log(f"📦 Found Job {job.id} ({job.type}). Launching Task...")
                    
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
    log(f"🚀 Starting Task for Job {job_id} [{job_type}]")
    try:
        if job_type == "intraday":
                data = await intra_scanner.run_scan(job_id)
        elif job_type == "swing_scan":
                data = await swing_scanner.run_scan(job_id)
        else:
                data = await longterm_scanner.run_scan(job_id, mode=job_type)
        
        # Mark Complete
        async with AsyncSessionLocal() as session:
            q = select(Job).where(Job.id == job_id)
            res = await session.execute(q)
            job = res.scalars().first()
            if job:
                from datetime import datetime
                from app.services.utils import sanitize_data
                job.status = "completed"
                job.updated_at = datetime.utcnow()
                job.result = sanitize_data(data)
                await session.commit()
                log(f"✅ Job {job_id} Completed Successfully.")

    except Exception as e:
        # Don't print here, we print below after marking failed
        # print(f"❌ Job {job_id} Failed: {e}")
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
                    log(f"❌ Job {job_id} Failed: {e}")
        except:
             log(f"Failed to save error state for {job_id}")

if __name__ == "__main__":
    try:
        import concurrent.futures
        # Increase default thread pool size for massive parallel yfinance fetches
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Use 300 to give plenty of headroom for timed-out but still draining sockets
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=300)
        loop.set_default_executor(executor)
        loop.run_until_complete(worker_loop())
    except KeyboardInterrupt:
        print("Worker Stopped.")
