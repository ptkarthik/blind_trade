import asyncio
import uuid
from app.services.swing_engine import SwingEngine
from app.db.session import AsyncSessionLocal
from app.models.job import Job

async def run_test_swing():
    engine = SwingEngine()
    job_id = str(uuid.uuid4())
    print(f"Starting test swing job: {job_id}")
    
    # Run scan on a small list
    symbols = ["VIJAYA.NS", "COALINDIA.NS", "INDIAGLYCO.NS"]
    
    async with AsyncSessionLocal() as session:
        job = Job(id=job_id, type="swing_scan", status="processing")
        session.add(job)
        await session.commit()
    
    engine.start_job(job_id)
    results = []
    for s in symbols:
        print(f"Analyzing {s}...")
        res = await engine.analyze_stock(s, job_id)
        if res:
            print(f"  Match! Signal: {res.get('signal')}")
            results.append(res)
            
    # Save final results
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        res_job = await session.execute(select(Job).where(Job.id == job_id))
        job_obj = res_job.scalars().first()
        job_obj.result = {"data": results, "total_scanned": len(symbols), "status_msg": "Completed"}
        job_obj.status = "completed"
        await session.commit()
        
    print("Test swing job completed.")

if __name__ == "__main__":
    asyncio.run(run_test_swing())
