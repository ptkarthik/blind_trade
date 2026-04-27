import asyncio
import sys
import os

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select

async def main():
    async with AsyncSessionLocal() as db:
        query = select(Job).where(Job.type == 'swing_scan').order_by(Job.created_at.desc()).limit(1)
        result = await db.execute(query)
        job = result.scalars().first()
        
        if not job:
            print("No swing scan jobs found.")
            return

        print(f"Job ID: {job.id}")
        print(f"Status: {job.status}")
        print(f"Created: {job.created_at}")
        
        res = job.result
        if isinstance(res, dict):
            active = res.get('active_symbols', [])
            data = res.get('data', [])
            print(f"Active Symbols Checked: {len(active)}")
            print(f"Setup Matches Found (data len): {len(data)}")
            
            # Count actual HIGH/MEDIUM signals
            matches = [d for d in data if d.get('signal') != 'IGNORE']
            print(f"Non-IGNORE Matches: {len(matches)}")
            
            if len(matches) > 0:
                print("First Match:", matches[0]['symbol'])
            if len(data) > 0:
                print("Total data payload length:", len(str(data)))
        else:
            print("Result is not a dict:", type(res))

if __name__ == "__main__":
    asyncio.run(main())
