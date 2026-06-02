import asyncio
import json
from app.db.session import AsyncSessionLocal
from sqlalchemy import select
from app.models.job import Job

async def check_swing_db():
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Job).where(Job.type == "swing_scan", Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        )
        job = res.scalar_one_or_none()
        
        if not job:
            print("No swing job found.")
            return
            
        data = job.result if job.result else []
        if isinstance(data, str):
            data = json.loads(data)
            
        print(f"Data type: {type(data)}")
        if isinstance(data, dict):
            print(f"Keys: {list(data.keys())}")
            # If data has a 'data' key, use that
            if 'data' in data:
                data = data['data']
        
        for stock in data:
            if isinstance(stock, dict) and stock.get("symbol") in ["TPLPLASTEH.NS", "MOTHERSON.NS"]:
                print(f"\n--- {stock.get('symbol')} ---")
                print(f"Final Score: {stock.get('score')}")
                print(f"Base Score: {stock.get('base_score')}")
                print(f"Signal: {stock.get('signal')}")
                print(f"AI Approved: {stock.get('ai_approved')}")
                print(f"AI Score: {stock.get('ai_confidence')}")
                print(f"AI Reason: {stock.get('ai_reason')}")
                print(f"Flags: {stock.get('flags')}")
                print(f"Reasons / Penalties:")
                for r in stock.get('reasons', []):
                    print(f"  - {r}")

if __name__ == "__main__":
    asyncio.run(check_swing_db())
