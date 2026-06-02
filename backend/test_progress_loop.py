import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
from app.services.utils import sanitize_data
from sqlalchemy.orm.attributes import flag_modified

async def test_update():
    job_id = "f9a81178-2171-4402-9e86-7d7ed13ca571"
    try:
        async with AsyncSessionLocal() as session:
            job = await session.get(Job, job_id)
            if job:
                print("Found job!")
                state_results = []
                job.result = sanitize_data({
                    "progress": 0, "total_steps": 1458,
                    "data": sorted(
                        state_results,
                        key=lambda x: (x.get("score", 0), -(x.get("analysis_index", 0))),
                        reverse=True
                    )[:500],
                    "status_msg": f"V11 Pulse Scan: 0/1458"
                })
                flag_modified(job, "result")
                await session.commit()
                print("Commit successful!")
            else:
                print("Job not found")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_update())
