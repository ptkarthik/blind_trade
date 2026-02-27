
import asyncio
from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from datetime import datetime, timedelta

async def clear_stale_jobs():
    async with AsyncSessionLocal() as session:
        print(f"--- Clearing Stale Jobs at {datetime.now()} ---")
        
        # Mark all 'processing' or 'pending' jobs as 'failed'
        # if they haven't been updated for 15 minutes
        stale_threshold = datetime.utcnow() - timedelta(minutes=15)
        
        stmt = (
            update(Job)
            .where(Job.status.in_(['processing', 'pending']))
            .where(Job.updated_at < stale_threshold)
            .values(
                status='failed',
                error_details="System Restarted: Stale job cleared automatically.",
                updated_at=datetime.utcnow()
            )
        )
        
        result = await session.execute(stmt)
        await session.commit()
        
        print(f"Cleared {result.rowcount} stale jobs.")

if __name__ == "__main__":
    asyncio.run(clear_stale_jobs())
