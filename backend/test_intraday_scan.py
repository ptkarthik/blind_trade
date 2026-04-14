import sys
import os
sys.path.append(os.getcwd())
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from app.services.intraday_engine import intraday_engine
from app.services.worker_logger import get_worker_logger
import uuid
import datetime

async def test_scan():
    print("Initializing test scan job...")
    job_id = str(uuid.uuid4())
    async with AsyncSessionLocal() as session:
        new_job = Job(id=job_id, type="intraday", status="pending", trigger_source="manual")
        session.add(new_job)
        await session.commit()
    
    print(f"Created Job {job_id} in Database. Starting scan...")
    logger = get_worker_logger(job_id, "TEST", "intraday")
    
    start_time = datetime.datetime.now()
    results = await intraday_engine.run_scan(job_id, logger=logger)
    end_time = datetime.datetime.now()
    
    print(f"Scan Finished in {(end_time - start_time).total_seconds()} seconds.")
    print("Summary of results:")
    print(f"- Total processed: {results.get('total')}")
    print(f"- Success models: {results.get('success')}")
    
    # Just show top 5
    dataList = results.get("data", [])
    print(f"- Data elements: {len(dataList)}")
    for i, res in enumerate(dataList[:5]):
        print(f"  {i+1}: {res['symbol']} Score={res.get('score')} Mode={res.get('alpha_mode')} Signal={res.get('signal')}")

if __name__ == "__main__":
    asyncio.run(test_scan())
