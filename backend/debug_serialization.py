
import asyncio
import json
import math
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy.future import select

async def check_serialization():
    print("--- Checking JSON Serialization of Job Data ---")
    async with AsyncSessionLocal() as session:
        query = select(Job).where(Job.status == "completed").order_by(Job.created_at.desc()).limit(1)
        result = await session.execute(query)
        job = result.scalars().first()
        
        if not job or not job.result:
            print("No job data found.")
            return

        data = job.result.get("data", [])
        print(f"Checking {len(data)} records...")
        
        try:
            # Attempt to serialize
            json_str = json.dumps(data)
            print("✅ Serialization Successful!")
        except Exception as e:
            print(f"❌ Serialization FAILED: {e}")
            
            # Find the culprit
            for idx, item in enumerate(data):
                try:
                    json.dumps(item)
                except Exception as inner_e:
                    print(f"Error in record {idx} ({item.get('symbol')}): {inner_e}")
                    # Check for NaNs
                    for k, v in item.items():
                        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                            print(f"  -> Found Bad Float in '{k}': {v}")

if __name__ == "__main__":
    asyncio.run(check_serialization())
