import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

async def test_update():
    job_id = "f9a81178-2171-4402-9e86-7d7ed13ca571"
    
    # 1. Write the initial progress (Simulate _progress_loop)
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        job.result = {"progress": 10, "total_steps": 1458, "status_msg": "Scanning"}
        flag_modified(job, "result")
        await session.commit()
        
    # 2. Simulate worker_main completion
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        data = {"total": 1458, "success": 0, "data": []}
        
        if not job.result:
            job.result = data
        else:
            current = job.result
            if isinstance(current, dict):
                current.update(data)
                job.result = current
        
        flag_modified(job, "result")
        await session.commit()
        
    # 3. Read it back
    async with AsyncSessionLocal() as session:
        job = await session.get(Job, job_id)
        print("FINAL DB RESULT:", job.result)

asyncio.run(test_update())
