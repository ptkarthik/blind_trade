import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job

async def check():
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Job).where(Job.type == "intraday", Job.status == "completed").order_by(Job.updated_at.desc()).limit(1)
        )
        job = res.scalars().first()
        data = job.result.get("data", [])
        
        for d in data[:15]:
            print(f"Symbol: {d['symbol']}, Score: {d['score']}, Signal: {d['signal']}, AI Approved: {d.get('ai_approved')}, AI Veto: {d.get('ai_reason')}")

asyncio.run(check())
