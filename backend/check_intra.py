import asyncio
import json
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job

async def check_intraday_db():
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Job).where(Job.type == "intraday", Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        )
        job = res.scalar_one_or_none()
        
        if not job:
            print("No intraday job found.")
            return
            
        data = job.result if job.result else []
        if isinstance(data, str):
            data = json.loads(data)
            
        if isinstance(data, dict):
            if 'data' in data:
                data = data['data']
        
        buys = 0
        sells = 0
        holds = 0
        
        for stock in data:
            if isinstance(stock, dict):
                sig = stock.get("signal", "")
                if "BUY" in sig:
                    buys += 1
                elif "SELL" in sig:
                    sells += 1
                else:
                    holds += 1
                    
        print(f"Total: {len(data)}")
        print(f"Buys: {buys}")
        print(f"Sells: {sells}")
        print(f"Holds: {holds}")

if __name__ == "__main__":
    asyncio.run(check_intraday_db())
