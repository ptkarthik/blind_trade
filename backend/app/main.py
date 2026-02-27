from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.market_data import market_service

import os
# PROXY BYPASS (Fix for N/A values and Connectivity issues)
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

import sys
print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: __file__: {__file__}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    await market_service.initialize()
    
    # Reset any stuck jobs from previous runs
    from app.db.session import AsyncSessionLocal
    from app.models.job import Job
    from sqlalchemy import select
    
    async with AsyncSessionLocal() as session:
        # Reset any stuck jobs (Processing, Paused, or old Pending)
        result = await session.execute(
            select(Job).where(Job.status.in_(["processing", "paused", "pending"]))
        )
        stuck_jobs = result.scalars().all()
        for job in stuck_jobs:
            print(f"⚠️ Clearing stale job {job.id} ({job.status})")
            job.status = "failed"
            job.error_details = "System restarted while job was active."
            if not job.result: job.result = {}
            job.result["status_msg"] = "Cleaned up on Restart"
            session.add(job)
        if stuck_jobs:
            await session.commit()
            
    # Background Runner is now handled by external Worker process (app.worker.worker_main)
    print("API Startup Complete. Background Jobs System Ready.")

from fastapi.staticfiles import StaticFiles
import os

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression for large JSON payloads (Fast Toggles)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount Reports for Visualization
if not os.path.exists("app/reports"):
    os.makedirs("app/reports")
app.mount("/reports", StaticFiles(directory="app/reports"), name="reports")

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Blind Trade API is running", "status": "OK"}
