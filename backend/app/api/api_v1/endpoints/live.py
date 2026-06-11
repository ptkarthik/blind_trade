from fastapi import APIRouter, HTTPException
from app.services.live_monitor import live_monitor

router = APIRouter()

@router.get("/")
async def get_live_dashboard(
    date: str = None
):
    """
    Get the live dashboard data containing top 10 stocks and active alerts.
    """
    data = await live_monitor.get_live_dashboard(scan_date=date)
    return data

@router.post("/run")
async def trigger_live_monitor():
    """
    Manually trigger the live monitor check.
    """
    import asyncio
    asyncio.create_task(live_monitor.run_intraday_check())
    return {"status": "started", "message": "Live monitor check triggered in background."}
