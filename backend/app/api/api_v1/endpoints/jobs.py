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
    type: str # 'full_scan', 'sector_scan', 'intraday', or 'swing_scan'

class JobSchema(BaseModel):
    id: str
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

@router.get("/status", response_model=Optional[JobSchema])
async def get_scan_status(job_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Get the latest job status from the last 24 hours, optionally filtered by type.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import desc, func
    
    since = datetime.utcnow() - timedelta(hours=24)
    
    # Extract only what we need for progress polling from the massive JSON blob
    query = select(
        Job.id, 
        Job.type, 
        Job.status, 
        Job.error_details, 
        Job.created_at, 
        Job.updated_at,
        func.json_extract(Job.result, '$.progress').label("progress"),
        func.json_extract(Job.result, '$.total_steps').label("total_steps"),
        func.json_extract(Job.result, '$.status_msg').label("status_msg")
    ).where(Job.created_at >= since)
    
    if job_type:
        query = query.where(Job.type == job_type)
        
    query = query.order_by(
        desc(Job.status == "processing"), 
        Job.updated_at.desc()
    ).limit(1)
    
    result = await db.execute(query)
    row = result.first()
    
    if not row:
        return None
        
    # Reconstruct a lightweight dict matching JobSchema
    return {
        "id": row.id,
        "type": row.type,
        "status": row.status,
        "error_details": row.error_details,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "result": {
            "progress": row.progress or 0,
            "total_steps": row.total_steps or 0,
            "status_msg": row.status_msg or ""
        }
    }

@router.get("/history", response_model=List[JobSchema])
async def get_scan_history(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    """
    Get job history from the last 24 hours.
    """
    from datetime import datetime, timedelta
    from sqlalchemy import func
    
    since = datetime.utcnow() - timedelta(hours=24)
    
    # Extract only what we need for history view (id, type, status, dates)
    query = select(
        Job.id, 
        Job.type, 
        Job.status, 
        Job.error_details, 
        Job.created_at, 
        Job.updated_at,
        func.json_extract(Job.result, '$.progress').label("progress"),
        func.json_extract(Job.result, '$.total_steps').label("total_steps"),
        func.json_extract(Job.result, '$.status_msg').label("status_msg")
    ).where(Job.created_at >= since).order_by(Job.created_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    rows = result.all()
    
    jobs_out = []
    for row in rows:
        jobs_out.append({
            "id": row.id,
            "type": row.type,
            "status": row.status,
            "error_details": row.error_details,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "result": {
                "progress": row.progress or 0,
                "total_steps": row.total_steps or 0,
                "status_msg": row.status_msg or ""
            }
        })
    return jobs_out

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
    
    # Active Kill Switch
    job_id_str = str(job.id)
    if job.type == "intraday":
        from app.services.intraday_engine import intraday_engine
        await intraday_engine.stop_job(job_id_str)
    else:
        # full_scan, sector_scan, etc.
        from app.services.scanner_engine import longterm_scanner_engine
        await longterm_scanner_engine.stop_job(job_id_str)
        
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
    
    # Pause Signal
    job_id_str = str(job.id)
    if job.type == "intraday":
        from app.services.intraday_engine import intraday_engine
        await intraday_engine.pause_job(job_id_str)
    else:
        from app.services.scanner_engine import longterm_scanner_engine
        await longterm_scanner_engine.pause_job(job_id_str)
        
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
    
    # Resume Signal
    job_id_str = str(job.id)
    if job.type == "intraday":
        from app.services.intraday_engine import intraday_engine
        await intraday_engine.resume_job(job_id_str)
    else:
        from app.services.scanner_engine import longterm_scanner_engine
        await longterm_scanner_engine.resume_job(job_id_str)
        
    return job

@router.get("/{job_id}/results")
async def get_job_results(job_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the full results data for a specific job.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Return just the data part of the result if it exists
    if job.result and isinstance(job.result, dict) and "data" in job.result:
        return job.result["data"]
    
    return job.result
