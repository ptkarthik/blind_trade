
import asyncio
import json
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def inspect():
    async with AsyncSessionLocal() as session:
        # Get latest COMPLETED full_scan
        stmt = select(Job).where(Job.type == "full_scan", Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
        if not job:
            print("No completed full_scan found.")
            return

        print(f"Inspecting Job: {job.id}, Created: {job.created_at}")
        data = job.result.get("data", [])
        
        # Look for GMDCLTD.NS
        target = next((item for item in data if item["symbol"] == "GMDCLTD.NS"), None)
        if target:
            print(f"Symbol: {target['symbol']}")
            print(f"LTP: {target['price']}, Smart Entry: {target['entry']}")
            print(f"Rationale: {target.get('verdict', 'N/A')}")
            print(f"Internal Rationale: {target.get('rationale', 'N/A')}")
            # Check the strategic_summary if it exists
            print(f"Strategic Summary: {target.get('strategic_summary', 'N/A')}")
        else:
            print("GMDCLTD.NS not found in this job.")

if __name__ == "__main__":
    asyncio.run(inspect())
