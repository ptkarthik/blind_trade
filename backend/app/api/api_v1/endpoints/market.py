from fastapi import APIRouter, HTTPException
from app.services.market_data import market_service

router = APIRouter()

@router.get("/status")
async def get_market_status():
    """
    Get current market status (Open/Closed) and major index levels.
    """
    data = await market_service.get_market_status()
    return data

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
