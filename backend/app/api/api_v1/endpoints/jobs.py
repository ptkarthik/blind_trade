from app.models.job import Job
from app.db.session import AsyncSessionLocal, get_db
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import List, Optional, Any
import uuid


router = APIRouter()

router = APIRouter()

# Schema
class JobCreate(BaseModel):
    type: str = "full_scan" # full_scan or sector_scan

class JobSchema(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    result: Optional[Any]
    error_details: Optional[str]
    created_at: Any # Date

    class Config:
        from_attributes = True

@router.post("/scan", response_model=JobSchema)
async def trigger_scan(job_in: JobCreate, db: AsyncSession = Depends(get_db)):
    """
    Trigger a new Background Scan Job.
    """
    # Check if a pending job of the SAME type already exists
    query = select(Job).where(Job.type == job_in.type, Job.status.in_(["pending", "processing"]))
    result = await db.execute(query)
    existing = result.scalars().first()
    
    if existing:
        return existing

    new_job = Job(type=job_in.type, status="pending")
    db.add(new_job)
    await db.commit()
    await db.refresh(new_job)
    
    return new_job

@router.get("/status", response_model=JobSchema)
async def get_scan_status(job_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Get the latest job status, optionally filtered by type.
    """
    query = select(Job)
    if job_type:
        query = query.where(Job.type == job_type)
    
    query = query.order_by(Job.created_at.desc()).limit(1)
    result = await db.execute(query)
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail=f"No {type or 'scan'} jobs found")
    return job

@router.get("/history", response_model=List[JobSchema])
async def get_scan_history(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    query = select(Job).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    jobs = result.scalars().all()
    return jobs

@router.post("/stop", response_model=JobSchema)
async def stop_scan(job_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Mark the latest active job as stopped.
    """
    query = select(Job).where(Job.status.in_(["pending", "processing", "paused"]))
    if job_type:
        query = query.where(Job.type == job_type)
        
    query = query.order_by(Job.created_at.desc()).limit(1)
    result = await db.execute(query)
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail=f"No active {job_type or ''} scan to stop")
    
    job.status = "stopped"
    await db.commit()
    await db.refresh(job)
    return job

@router.post("/pause", response_model=JobSchema)
async def pause_scan(job_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Pause the latest processing job.
    """
    query = select(Job).where(Job.status == "processing")
    if job_type:
        query = query.where(Job.type == job_type)
        
    query = query.order_by(Job.created_at.desc()).limit(1)
    result = await db.execute(query)
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail=f"No processing {job_type or ''} scan to pause")
    
    job.status = "paused"
    await db.commit()
    await db.refresh(job)
    return job

@router.post("/resume", response_model=JobSchema)
async def resume_scan(job_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Resume the latest paused job.
    """
    query = select(Job).where(Job.status == "paused")
    if job_type:
        query = query.where(Job.type == job_type)
        
    query = query.order_by(Job.created_at.desc()).limit(1)
    result = await db.execute(query)
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail=f"No paused {job_type or ''} scan to resume")
    
    job.status = "processing"
    await db.commit()
    await db.refresh(job)
    return job
