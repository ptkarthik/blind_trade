
import asyncio
import sys
import os
import json
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job

# Ensure backend dir is in path
sys.path.append(os.getcwd())

async def inspect_errors():
    async with AsyncSessionLocal() as session:
        # Get latest job
        query = select(Job).order_by(Job.created_at.desc()).limit(1)
        result = await session.execute(query)
        job = result.scalars().first()
        
        if not job:
            print("No jobs found.")
            return

        print(f"Job ID: {job.id}")
        print(f"Status: {job.status}")
        
        res_data = job.result
        if res_data and "errors" in res_data:
            errors = res_data["errors"]
            print(f"Total Errors: {len(errors)}")
            print("--- Error Log ---")
            for e in errors:
                print(e)
        else:
            print("No errors logged in result.")

if __name__ == "__main__":
    asyncio.run(inspect_errors())
