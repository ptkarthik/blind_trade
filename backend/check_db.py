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
        if not job:
            print("No job found")
            return
            
        print(f"Job ID: {job.id}")
        print(f"Is Hidden: {job.is_hidden}")
        
        data = job.result.get("data", []) if job.result else []
        print(f"Total signals: {len(data)}")
        
        buys = [s for s in data if s.get("signal") in ["BUY", "BUY_STRONG"]]
        print(f"Buys count: {len(buys)}")
        if buys:
            print(f"Sample buy symbol: {buys[0]['symbol']} (Score: {buys[0]['score']}, Signal: {buys[0]['signal']}, Action: {buys[0].get('action')})")
            
        holds = [s for s in data if s.get("signal") in ["HOLD", "NEUTRAL"]]
        print(f"Holds count: {len(holds)}")
        if holds:
            print(f"Sample hold symbol: {holds[0]['symbol']} (Score: {holds[0]['score']}, Signal: {holds[0]['signal']}, Action: {holds[0].get('action')})")

asyncio.run(check())
