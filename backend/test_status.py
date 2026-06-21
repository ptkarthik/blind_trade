import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
from sqlalchemy import desc, func
import time
from datetime import datetime, timedelta
import sys
import codecs

# Fix console encoding for Windows
sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

async def test():
    async with AsyncSessionLocal() as db:
        since = datetime.utcnow() - timedelta(hours=24)
        select_fields = [
            Job.id, 
            Job.type, 
            Job.status, 
            Job.error_details, 
            Job.created_at, 
            Job.updated_at,
            Job.trigger_source,
            Job.is_hidden,
            func.json_extract(Job.result, '$.progress').label('progress'),
            func.json_extract(Job.result, '$.total_steps').label('total_steps'),
            func.json_extract(Job.result, '$.status_msg').label('status_msg')
        ]
        
        t0 = time.time()
        query = select(*select_fields).where(Job.created_at >= since, Job.is_hidden == False).order_by(desc(Job.status == 'processing'), Job.created_at.desc()).limit(1)
        result = await db.execute(query)
        row = result.first()
        t1 = time.time()
        print(f'Query with json_extract took {t1-t0:.4f}s')

        # Test optimized query
        t0 = time.time()
        base_query = select(Job.id).where(Job.created_at >= since, Job.is_hidden == False).order_by(desc(Job.status == 'processing'), Job.created_at.desc()).limit(1)
        job_id_res = await db.execute(base_query)
        job_id = job_id_res.scalar()
        if job_id:
            query2 = select(*select_fields).where(Job.id == job_id)
            await db.execute(query2)
        t2 = time.time()
        print(f'Optimized Query took {t2-t0:.4f}s')

asyncio.run(test())
