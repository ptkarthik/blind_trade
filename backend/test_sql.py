import asyncio
from sqlalchemy import select, desc
from app.db.session import AsyncSessionLocal
from app.models.job import Job

async def test():
    async with AsyncSessionLocal() as session:
        query = select(Job.id, Job.status, Job.type, Job.updated_at).where(
            Job.type == 'intraday',
            Job.status.in_(["completed", "processing", "stopped"])
        ).order_by(
            desc(Job.status == 'processing'),
            Job.result.isnot(None).desc(),
            Job.updated_at.desc()
        ).limit(5)
        
        res = await session.execute(query)
        print("RESULTS IN ORDER:")
        for row in res.fetchall():
            print(f"ID: {row.id}, Status: {row.status}, Type: {row.type}, Updated: {row.updated_at}")

        print("\nNow looking for 'processing' jobs without filters:")
        q2 = select(Job.id, Job.status, Job.type).where(Job.status == 'processing')
        r2 = await session.execute(q2)
        for row in r2.fetchall():
            print(row)

asyncio.run(test())
