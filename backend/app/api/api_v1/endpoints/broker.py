from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.services.kite_data import kite_data

router = APIRouter()

class OrderRequest(BaseModel):
    symbol: str
    quantity: int
    transaction_type: str # 'BUY' or 'SELL'
    order_type: str = "MARKET"
    price: float = 0.0

@router.get("/margins", response_model=Dict[str, Any])
async def get_margins(
    current_user: dict = Depends(get_current_user),
) -> Any:
    """
    Get live Kite funding/margins.
    """
    result = await kite_data.get_margins()
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])
    return result

@router.post("/order", response_model=Dict[str, Any])
async def place_order(
    req: OrderRequest,
    current_user: dict = Depends(get_current_user),
) -> Any:
    """
    Place a real order via Kite.
    """
    result = await kite_data.place_order(
        symbol=req.symbol,
        quantity=req.quantity,
        transaction_type=req.transaction_type,
        order_type=req.order_type,
        price=req.price
    )
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Order failed"))
    return result
