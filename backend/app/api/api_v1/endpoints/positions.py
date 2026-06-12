from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Any, List
from sqlalchemy.orm import Session
from app.db.session import AsyncSessionLocal
from sqlalchemy import select

from app.services.position_manager import position_manager
from app.models.swing_trade import SwingTrade

router = APIRouter()

@router.get("/portfolio", response_model=List[dict])
async def get_portfolio() -> Any:
    """
    Get all active positions with live HOLD/SELL evaluations.
    """
    portfolio = await position_manager.get_live_portfolio()
    return portfolio

async def _manual_evaluation_task():
    await position_manager.run_evaluation_cycle()
    await position_manager.run_hourly_deep_scan(title="MANUAL EVALUATION SUMMARY")

@router.post("/evaluate_now")
async def trigger_evaluation() -> Any:
    """
    Manually trigger the evaluation loop and wait for it to complete.
    """
    await _manual_evaluation_task()
    return {"status": "Evaluation cycle completed"}

@router.post("/add_trade")
async def add_trade(trade_data: dict) -> Any:
    """
    Manually add a trade to track.
    (Ideally this is hit when user clicks 'I bought this' on the UI)
    """
    try:
        async with AsyncSessionLocal() as session:
            new_trade = SwingTrade(
                symbol=trade_data.get("symbol"),
                strategy=trade_data.get("strategy", "UNKNOWN"),
                entry=trade_data.get("entry_price"),
                stop_loss=trade_data.get("stop_loss"),
                initial_stop_loss=trade_data.get("stop_loss"),
                target=trade_data.get("target"),
                quantity=trade_data.get("quantity", 1),
                initial_score=float(trade_data.get("score", 0.0)),
                current_score=float(trade_data.get("score", 0.0)),
                scan_data=trade_data.get("full_scan_data"),
                initial_scan_data=trade_data.get("full_scan_data"),
                status="OPEN"
            )
            session.add(new_trade)
            await session.commit()
            return {"status": "Success", "trade_id": new_trade.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/close/{trade_id}")
async def close_trade(trade_id: str) -> Any:
    """
    Manually close an active position.
    """
    try:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(SwingTrade).where(SwingTrade.id == trade_id))
            trade = res.scalars().first()
            if not trade:
                raise HTTPException(status_code=404, detail="Trade not found")
            
            trade.status = "CLOSED"
            await session.commit()
            return {"status": "Success", "message": "Trade closed manually"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
