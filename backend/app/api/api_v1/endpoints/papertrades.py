
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.papertrade import Account, PaperTrade
from app.services.market_data import market_service
from app.services.utils import sanitize_data
import datetime
import uuid

router = APIRouter()

async def get_or_create_account(db: AsyncSession):
    """
    Ensures a virtual account exists.
    """
    result = await db.execute(select(Account).limit(1))
    account = result.scalars().first()
    if not account:
        account = Account(balance=1000000.0) # 10 Lakhs default
        db.add(account)
        await db.commit()
        await db.refresh(account)
    return account

@router.get("/account")
async def get_account_info(db: AsyncSession = Depends(get_db)):
    account = await get_or_create_account(db)
    return sanitize_data({
        "balance": account.balance,
        "total_pnl": account.total_pnl,
        "updated_at": account.updated_at
    })

@router.post("/buy")
async def place_paper_order(order_data: dict, db: AsyncSession = Depends(get_db)):
    """
    Places a paper trading buy order.
    Expected order_data: {symbol, qty, price, target, stop_loss, score}
    """
    symbol = order_data.get("symbol")
    qty = order_data.get("qty")
    price = order_data.get("price")
    
    if not symbol or not qty or not price:
        raise HTTPException(status_code=400, detail="Missing order details")
    
    account = await get_or_create_account(db)
    total_cost = qty * price
    
    if account.balance < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient virtual balance")
    
    # Deduct balance
    account.balance -= total_cost
    
    # Create trade
    new_trade = PaperTrade(
        symbol=symbol,
        qty=qty,
        buy_price=price,
        target=order_data.get("target"),
        stop_loss=order_data.get("stop_loss"),
        score_at_buy=order_data.get("score"),
        status="OPEN"
    )
    
    db.add(new_trade)
    await db.commit()
    return {"status": "success", "trade_id": new_trade.id, "remaining_balance": account.balance}

@router.get("/trades")
async def get_paper_trades(db: AsyncSession = Depends(get_db)):
    """
    Lists all paper trades.
    """
    result = await db.execute(select(PaperTrade).order_by(PaperTrade.buy_time.desc()))
    trades = result.scalars().all()
    return sanitize_data(trades)

@router.patch("/close/{trade_id}")
async def close_paper_trade(trade_id: str, db: AsyncSession = Depends(get_db)):
    """
    Closes an open paper trade at the current market price.
    """
    result = await db.execute(select(PaperTrade).where(PaperTrade.id == trade_id, PaperTrade.status == "OPEN"))
    trade = result.scalars().first()
    
    if not trade:
        raise HTTPException(status_code=404, detail="Open trade not found")
    
    # Get latest price
    current_price = await market_service.get_latest_price(trade.symbol)
    if not current_price:
        raise HTTPException(status_code=500, detail="Could not fetch current market price")
    
    # Update trade
    trade.sell_price = current_price
    trade.sell_time = datetime.datetime.utcnow()
    trade.status = "CLOSED"
    
    # Update account balance and P&L
    account = await get_or_create_account(db)
    proceeds = trade.qty * current_price
    pnl = proceeds - (trade.qty * trade.buy_price)
    
    account.balance += proceeds
    account.total_pnl += pnl
    
    await db.commit()
    return {"status": "closed", "sell_price": current_price, "pnl": pnl, "new_balance": account.balance}

@router.post("/reset_account")
async def reset_paper_trading(db: AsyncSession = Depends(get_db)):
    """
    Resets account balance and clears trade history.
    """
    account = await get_or_create_account(db)
    account.balance = 1000000.0
    account.total_pnl = 0.0
    
    # Note: For safety, maybe keep the history but mark as 'legacy'? 
    # For a simple 'dummy money' reset, let's just reset the balance.
    await db.commit()
    return {"status": "reset", "balance": account.balance}
