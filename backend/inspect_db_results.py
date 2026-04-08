import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
from sqlalchemy import desc

async def inspect_results():
    async with AsyncSessionLocal() as session:
        query = select(Job).where(Job.type == "intraday").order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(query)
        job = res.scalars().first()
        
        if not job:
            print("No intraday job found.")
            return
            
        print(f"Job ID: {job.id}, Status: {job.status}, Updated: {job.updated_at}")
        if job.result:
            data = job.result.get("data", [])
            print(f"Total results in data: {len(data)}")
            if data:
                # Group by signal
                stats = {}
                for s in data:
                    sig = s.get("signal", "NONE")
                    stats[sig] = stats.get(sig, 0) + 1
                
                print("Signal counts:", stats)
                
                # Show top 5
                print("\nTop 5 results:")
                for s in data[:5]:
                    print(f" - {s['symbol']}: Score={s['score']}, Signal={s['signal']}, Sector={s.get('sector')}")
            else:
                print("Result data is empty.")
        else:
            print("Job result is None.")

if __name__ == "__main__":
    asyncio.run(inspect_results())
