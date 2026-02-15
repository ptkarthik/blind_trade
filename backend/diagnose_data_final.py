
import asyncio
import json
import os
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def run_diag():
    output = []
    async with AsyncSessionLocal() as session:
        # Get latest job of any type
        stmt = select(Job).order_by(Job.created_at.desc()).limit(5)
        res = await session.execute(stmt)
        jobs = res.scalars().all()
        
        for job in jobs:
            output.append(f"Job ID: {job.id}, Type: {job.type}, Status: {job.status}, Created: {job.created_at}")
            data = job.result.get("data", [])
            if data:
                output.append(f"  First item symbol: {data[0].get('symbol')}")
                output.append(f"  First item rationale: {data[0].get('verdict')}")
            else:
                output.append("  No data in job yet.")
            output.append("-" * 20)

    with open("diag_output.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    print("Diagnostics written to diag_output.txt")

if __name__ == "__main__":
    asyncio.run(run_diag())
