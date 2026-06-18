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
            result = await session.execute(
                select(Job).where(Job.type == job_type).order_by(Job.created_at.desc())
            )
            latest_job = result.scalars().first()
            if latest_job:
                market_data["latest_job"] = {
                    "id": latest_job.id,
                    "status": latest_job.status,
                    "progress": latest_job.result.get("progress", 0) if latest_job.result else 0,
                    "total": latest_job.result.get("total_steps", 0) if latest_job.result else 0,
                    "status_msg": latest_job.result.get("status_msg", "") if latest_job.result else ""
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
