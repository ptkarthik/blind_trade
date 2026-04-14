import sys
import os

# FORCE UTF-8 BEFORE ANY OTHER IMPORTS
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.intraday_engine import intraday_engine
from app.services.worker_logger import get_worker_logger
import uuid
import datetime

async def test_scan():
    print("Initializing test scan job...", flush=True)
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        new_job = Job(id=job_id, type="intraday", status="pending", trigger_source="manual")
        session.add(new_job)
        await session.commit()
    
    print(f"Created Job {job_id} in Database. Starting scan...", flush=True)
    logger = get_worker_logger(job_id, "TEST", "intraday")
    
    start_time = datetime.datetime.now()
    results = await intraday_engine.run_scan(job_id, logger=logger)
    end_time = datetime.datetime.now()
    
    print(f"Scan Finished in {(end_time - start_time).total_seconds()} seconds.", flush=True)
    print("Summary of results:", flush=True)
    print(f"- Total processed: {results.get('total')}", flush=True)
    print(f"- Success models: {results.get('success')}", flush=True)
    
    dataList = results.get("data", [])
    print(f"- Data elements: {len(dataList)}", flush=True)

if __name__ == "__main__":
    asyncio.run(test_scan())
