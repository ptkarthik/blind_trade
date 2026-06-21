from fastapi import APIRouter, HTTPException
from app.services.market_data import market_service
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from typing import Optional

router = APIRouter()

@router.get("/status")
async def get_market_status(job_type: Optional[str] = None):
    """
    Get current market status + latest job progress for the Hub.
    """
    market_data = await market_service.get_market_status()
    
    # [V11 RESTORED] Dashboard-to-Engine Bridge
    if job_type:
        async with AsyncSessionLocal() as session:
            # Step 1: Find the latest job ID to avoid scanning/deserializing huge JSON blobs for multiple rows
            id_query = select(Job.id).where(Job.type == job_type).order_by(Job.created_at.desc()).limit(1)
            id_result = await session.execute(id_query)
            job_id = id_result.scalar()
            
            if job_id:
                from sqlalchemy import func
                row_query = select(
                    Job.id,
                    Job.status,
                    func.json_extract(Job.result, '$.progress').label("progress"),
                    func.json_extract(Job.result, '$.total_steps').label("total_steps"),
                    func.json_extract(Job.result, '$.status_msg').label("status_msg")
                ).where(Job.id == job_id)
                
                row_result = await session.execute(row_query)
                row = row_result.first()
                if row:
                    market_data["latest_job"] = {
                        "id": row.id,
                        "status": row.status,
                        "progress": row.progress or 0,
                        "total": row.total_steps or 0,
                        "status_msg": row.status_msg or ""
                    }
    
    return market_data

@router.get("/live/{symbol}")
async def get_live_price(symbol: str):
    """
    Get live price for a specific stock.
    """
    data = await market_service.get_live_price(symbol)
    if not data:
        raise HTTPException(status_code=404, detail="Stock not found")
    return data

@router.get("/search")
async def search_stocks(q: str):
    """
    Search for stocks by symbol or name.
    """
    if len(q) < 3:
        return []
    results = await market_service.search_symbols(q)
    return results

@router.get("/kite/status")
async def get_kite_status():
    """Returns Kite Connect connection status and login URL if needed."""
    from app.services.kite_data import kite_data
    return kite_data.get_status()

@router.post("/kite/login")
async def trigger_kite_login():
    """Re-initializes Kite Connect and returns login URL."""
    from app.services.kite_data import kite_data
    await kite_data.initialize()
    return kite_data.get_status()

import asyncio
@router.post("/macro-sync")
async def trigger_macro_sync():
    """Trigger background sync for 1D and 1H historical data via Kite."""
    from app.services.macro_cache import macro_cache
    if macro_cache.is_syncing:
        return {"status": "already_syncing", "message": "Macro Cache Sync is already running in the background."}
    
    asyncio.create_task(macro_cache.sync_cache())
    return {"status": "started", "message": "Macro Cache Sync started in the background. Check backend logs for progress."}
