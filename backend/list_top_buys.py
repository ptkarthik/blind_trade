
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def list_top_buys():
    async with AsyncSessionLocal() as session:
        query = select(Job).where(Job.type == "full_scan", Job.status == "completed").order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(query)
        job = res.scalars().first()
        
        if not job:
            print("No jobs found.")
            return
            
        print(f"Latest Job ID: {job.id} at {job.updated_at}")
        data = job.result.get("data", [])
        buys = sorted([s for s in data if s.get("signal") == "BUY"], key=lambda x: x.get("score", 0), reverse=True)
        
        print(f"Number of BUYS: {len(buys)}")
        for i, b in enumerate(buys[:15]):
            print(f"{i+1}. {b.get('symbol')}: {b.get('score')} | {b.get('sector')}")

if __name__ == "__main__":
    asyncio.run(list_top_buys())
