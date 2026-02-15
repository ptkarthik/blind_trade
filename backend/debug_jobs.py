
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job

async def check():
    async with AsyncSessionLocal() as session:
        # Show last 10 jobs of any type first to see context
        stmt = select(Job).order_by(Job.updated_at.desc()).limit(10)
        res = await session.execute(stmt)
        jobs = res.scalars().all()
        print("LAST 10 JOBS (All):")
        for j in jobs:
            err = (j.error_details[:50] + "...") if j.error_details and len(j.error_details) > 50 else j.error_details
            print(f"ID: {str(j.id)[:8]} | Type: {j.type:10} | Status: {j.status:10} | Error: {err or 'None'}")
        
        # Now specifically look for failed intraday jobs
        print("\nFAILED INTRADAY JOBS (Detailed):")
        stmt = select(Job).where(Job.type == "intraday", Job.status == "failed").order_by(Job.updated_at.desc()).limit(5)
        res = await session.execute(stmt)
        failed_jobs = res.scalars().all()
        for j in failed_jobs:
            print(f"ID: {str(j.id)} | Error: {j.error_details}")

if __name__ == "__main__":
    asyncio.run(check())
