import sys
import os
import socket
import io
# Ensure backend dir is in path BEFORE other imports
sys.path.append(os.getcwd())
backend_path = os.path.join(os.getcwd(), "backend")
if os.path.exists(backend_path):
    sys.path.append(backend_path)

# Prevent Unicode errors on Windows terminal
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        # Fallback to force utf-8 if reconfigure fails
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Prevent thread pool exhaustion from rogue hanging network requests
socket.setdefaulttimeout(15.0)

import asyncio
import time
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.models.setting import Setting
from app.services.scanner_engine import longterm_scanner_engine as longterm_scanner
from app.services.intraday_engine import intraday_engine as intra_scanner
from app.services.swing_engine import swing_engine as swing_scanner
from app.services.worker_logger import get_worker_logger
from app.utils.worker_lock import WorkerLock
from app.services.paper_monitor import paper_monitor


# Worker Mode Configuration
WORKER_TYPE = os.getenv("WORKER_TYPE", "all").lower()
# AUTO_SCHEDULE is now dynamic (Phase 89)
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
    import sys
    color_prefix = ""
    # Add simple visual distinction for different worker types
    if WORKER_TYPE == "longterm": color_prefix = "[LONG]"
    elif WORKER_TYPE == "intraday": color_prefix = "[INT]"
    elif WORKER_TYPE == "swing": color_prefix = "[SWING]"
    else: color_prefix = "[ALL]"
    
    timestamp = datetime.now().strftime('%H:%M:%S')
    output = f"[{timestamp}] {color_prefix} [ID-{WORKER_ID}] {msg}"
    
    try:
        print(output, flush=True)
    except UnicodeEncodeError:
        # Fallback for Windows consoles that don't support UTF-8/Emojis
        print(output.encode('ascii', 'ignore').decode('ascii'), flush=True)

log("="*60)
log(f"🛠️  Worker Initialized")
log(f"Handling: {', '.join(ALLOWED_JOB_TYPES)}")
log("="*60)

async def manage_recurring_scans():
    """
    Checks if 10 minutes have passed since the last scan of each type 
    and triggers a new one if needed.
    """
    from datetime import datetime, timedelta
    RECURRENCE_INTERVAL = timedelta(minutes=10)
    
    # Only check types this worker is responsible for (Phase 96: Intraday Auto-Only)
    types_to_check = [t for t in ["intraday"] if t in ALLOWED_JOB_TYPES]
    
    if not types_to_check:
        return
    
    async with AsyncSessionLocal() as session:
        # 0. Check Dynamic Setting (Phase 89: UI Toggle)
        res = await session.execute(select(Setting).where(Setting.key == "auto_restart"))
        setting = res.scalars().first()
        is_auto_on = setting.value.lower() == "true" if setting else True
        
        if not is_auto_on:
            return

        for job_type in types_to_check:
            # 1. Check if any job of this type is already pending or processing
            active_query = select(Job).where(Job.type == job_type, Job.status.in_(["pending", "processing"]))
            active_res = await session.execute(active_query)
            if active_res.scalars().first():
                continue # Already busy
            
            # 2. Timing Logic
            should_trigger = False
            
            if job_type == "intraday":
                # AUTO-RESTART: 5 minutes after last SUCCESSFUL completion (24/7 as requested)
                history_query = select(Job).where(Job.type == job_type, Job.status == "completed").order_by(Job.updated_at.desc()).limit(1)
                history_res = await session.execute(history_query)
                last_completed_job = history_res.scalars().first()
                
                if not last_completed_job:
                    should_trigger = True
                else:
                    elapsed = (datetime.utcnow() - last_completed_job.updated_at)
                    if elapsed > timedelta(minutes=5):
                        should_trigger = True
                    else:
                        msg = f"⏳ [SCHEDULER] {job_type}: Cooldown active. {5 - (elapsed.total_seconds()/60):.1f}m left."
                        if int(time.time()) % 60 < 2: log(msg) # Log once per minute roughly
            else:
                # Standard 10min recurrence for others
                history_query = select(Job).where(Job.type == job_type).order_by(Job.created_at.desc()).limit(1)
                history_res = await session.execute(history_query)
                last_job = history_res.scalars().first()
                
                if not last_job:
                    should_trigger = True
                else:
                    elapsed = datetime.utcnow() - last_job.updated_at
                    if elapsed >= RECURRENCE_INTERVAL: # 10m
                        should_trigger = True
            
            if should_trigger:
                # V16.1: Evasion Jitter (Random delay before trigger)
                import random
                jitter = random.randint(1, 15)  # V18 FIX #17: Reduced from 120s — 15s sufficient for de-correlation
                log(f"⏰ [SCHEDULER] Auto-triggering {job_type} (Jitter: {jitter}s)")
                await asyncio.sleep(jitter)
                
                # Phase 88: Auto-triggered scans are hidden from UI to avoid clutter
                hidden = True if job_type == "intraday" else False
                new_job = Job(type=job_type, status="pending", trigger_source="auto", is_hidden=hidden)
                session.add(new_job)
                await session.commit()

async def worker_loop():
    log(f"👷 Worker Process Started. PID: {os.getpid()}")
    
    # --- PHASE 95: Worker PID Lock (Process Isolation) ---
    lock = WorkerLock(WORKER_TYPE)
    if not lock.acquire():
        log(f"🚫 [FATAL] Another worker of type '{WORKER_TYPE}' is already running. Exiting...")
        sys.exit(1)
    
    log(f"✅ Lock Acquired for Type: {WORKER_TYPE}")
    
    try:
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
        
        active_tasks = set()
        MAX_CONCURRENT_JOBS = 6 # Increased from 3 to allow concurrent scans

        last_heartbeat = 0
        last_paper_check = 0
        while True:
            try:
                now = time.time()
                
                # Check Paper Trades every 30 seconds (Phase 102: Automated Monitoring)
                if now - last_paper_check > 30:
                    await paper_monitor.check_trades()
                    last_paper_check = now

                if now - last_heartbeat > 30:
                    log(f"💓 Worker Heartbeat (Type: {WORKER_TYPE}, Id: {WORKER_ID})")
                    last_heartbeat = now

                # 0. Manage Recurring Scans (Check every loop iteration, manage_recurring_scans handles timing)
                await manage_recurring_scans()

                # 1. Clean up finished tasks
                active_tasks = {t for t in active_tasks if not t.done()}
                
                # PREEMPTION: If a MANUAL job is pending, and an AUTO job of same type is running, Kill Auto.
                async with AsyncSessionLocal() as session:
                    # Get all active jobs from DB that are currently processing
                    active_q = select(Job).where(Job.status == "processing", Job.type.in_(ALLOWED_JOB_TYPES))
                    active_res = await session.execute(active_q)
                    processing_jobs = active_res.scalars().all()
                    
                    # Get all pending manual jobs
                    manual_q = select(Job).where(Job.status == "pending", Job.trigger_source == "manual", Job.type.in_(ALLOWED_JOB_TYPES))
                    manual_res = await session.execute(manual_q)
                    pending_manual_types = {j.type for j in manual_res.scalars().all()}
                    
                    for job in processing_jobs:
                        if job.trigger_source == "auto" and job.type in pending_manual_types:
                            log(f"⚡ [PREEMPTION] Manual {job.type} job detected. Cancelling auto-job {job.id}...")
                            # 1. Update DB status
                            job.status = "failed"
                            job.error_details = "Preempted by manual UI request."
                            job.updated_at = datetime.utcnow()
                            await session.commit()
                            
                            # 2. Stop the local engine task
                            if job.type == "intraday":
                                 await intra_scanner.stop_job(job.id)
                            elif job.type == "swing_scan":
                                 await swing_scanner.stop_job(job.id)
                            else:
                                 await longterm_scanner.stop_job(job.id)
                        
                        # Phase 105: Manual STOP Check Detection
                        if job.status == "stopped":
                            log(f"🛑 [STOP] Job {job.id} marked as STOPPED in DB. Terminating...")
                            if job.type == "intraday":
                                 await intra_scanner.stop_job(job.id)
                            elif job.type == "swing_scan":
                                 await swing_scanner.stop_job(job.id)
                            else:
                                 await longterm_scanner.stop_job(job.id)

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
                        
                        # --- V16.1 PROXY HEALTH PRE-CHECK ---
                        from app.services.proxy_manager import proxy_manager
                        proxies = await proxy_manager.get_proxy()
                        if not proxies:
                            log(f"⚠️ [SAFETY] No Healthy Proxies available. Delaying job {job.id}...")
                            await asyncio.sleep(10)
                            continue

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
    finally:
        # Ensure the lock is released when the worker_loop exits
        lock.release()
        log(f"🔒 Lock Released for Type: {WORKER_TYPE}")


async def process_job_task(job_id, job_type):
    """
    Wrapper to execute the scan and update DB status.
    Runs concurrently with WorkerLogger and SFTP upload.
    """
    logger = get_worker_logger(job_id, WORKER_ID, job_type)
    logger.info(f"🚀 Starting Task for Job {job_id} [{job_type}]")
    
    try:
        if job_type == "intraday":
                data = await intra_scanner.run_scan(job_id, logger=logger)
        elif job_type == "swing_scan":
                data = await swing_scanner.run_scan(job_id, logger=logger)
        else:
                data = await longterm_scanner.run_scan(job_id, mode=job_type, logger=logger)
        
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
                logger.info(f"✅ Job {job_id} Completed Successfully.")

    except Exception as e:
        logger.error(f"❌ Job {job_id} failed with critical error: {str(e)}")
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
                    logger.info(f"Logged failure status for {job_id} in DB.")
        except Exception as db_err:
             logger.error(f"Failed to save error state for {job_id}: {db_err}")
    finally:
        # PUSH LOG TO SFTP
        logger.info(f"Preparing to upload worker log for Job {job_id}...")
        await logger.upload_to_sftp()

async def cleanup_stuck_jobs():
    from app.db.session import AsyncSessionLocal
    from sqlalchemy import select, update
    from app.models.job import Job
    from datetime import datetime
    
    async with AsyncSessionLocal() as session:
        try:
            # Phase 91: Reset stuck processing jobs to failed so they don't block UI
            q = select(Job).where(Job.status == "processing", Job.type.in_(ALLOWED_JOB_TYPES))
            res = await session.execute(q)
            stuck_jobs = res.scalars().all()
            if stuck_jobs:
                log(f"🧹 Found {len(stuck_jobs)} stuck jobs. Resetting to failed...")
                for job in stuck_jobs:
                    job.status = "failed"
                    job.error_details = "Worker restarted during processing."
                    job.updated_at = datetime.utcnow()
                await session.commit()
        except Exception as e:
            log(f"⚠️  Cleanup failed: {e}")

if __name__ == "__main__":
    try:
        import concurrent.futures
        # Increase default thread pool size for massive parallel yfinance fetches
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        # Use 30 to give enough headroom without triggering immediate 429 IP Bans.
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=30)
        loop.set_default_executor(executor)
        
        # Run cleanup before entering main loop
        loop.run_until_complete(cleanup_stuck_jobs())
        
        loop.run_until_complete(worker_loop())
    except KeyboardInterrupt:
        print("Worker Stopped.")
    finally:
        pass
