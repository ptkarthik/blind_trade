
import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select
import json

async def check_db():
    async with AsyncSessionLocal() as session:
        # Get latest completed job
        stmt = select(Job).where(Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
        if not job:
            print("No completed jobs found.")
            return
            
        print(f"Latest Job ID: {job.id}")
        print(f"Updated At: {job.updated_at}")
        
        if not job.result:
            print("Job result is empty.")
            return
            
        data = job.result.get("data", [])
        print(f"Total Records: {len(data)}")
        
        if len(data) > 0:
            print("\n--- Sample Record (First Item) ---")
            item = data[0]
            # Print keys to see if 'sector' exists
            print(json.dumps(item, indent=2))
            
            if "sector" not in item:
                print("\n[ALERT] 'sector' key is MISSING in the data.")
            else:
                print(f"\n[OK] 'sector' found: {item['sector']}")
        else:
            print("Data list is empty.")

if __name__ == "__main__":
    asyncio.run(check_db())
