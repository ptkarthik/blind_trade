"""
[PERFORMANCE AUDIT] API Endpoints
==================================
Endpoints for viewing scan performance audits and triggering EOD evaluation.
"""

from fastapi import APIRouter
from app.services.performance_tracker import performance_tracker

router = APIRouter()


@router.get("/report")
async def get_audit_report(date: str = None):
    """
    Returns the full audit report for a given scan date.
    If no date is provided, defaults to today.
    
    Response includes per-stock performance, aggregate stats,
    and TRAP classification for stocks that lost > 2%.
    """
    return await performance_tracker.get_audit_report(date)


@router.post("/evaluate")
async def trigger_eod_evaluation(date: str = None):
    """
    Triggers end-of-day performance evaluation for tracked stocks.
    Fetches current/closing prices and calculates % change from entry.
    
    Call this at market close (~3:30 PM IST) or anytime to update.
    """
    return await performance_tracker.evaluate_eod_performance(date)


@router.get("/history")
async def get_audit_history(days: int = 7):
    """
    Returns summary stats for the last N days of scans.
    Useful for tracking scoring accuracy trends over time.
    """
    history = await performance_tracker.get_history(days)
    return {"status": "OK", "data": history}
