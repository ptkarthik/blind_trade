
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.models.papertrade import Account, PaperTrade
from app.services.market_data import market_service
from app.services.utils import sanitize_data
import datetime
from datetime import timezone, timedelta
import uuid
import asyncio

router = APIRouter()

# Global IST timezone for consistency
IST = timezone(timedelta(hours=5, minutes=30))

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
    
    # [FIX] Apply realistic 0.12% execution slippage to entry
    is_short = True if (order_data.get("stop_loss", 0) > price) else False
    entry_slip = price * 0.0012
    execution_price = price + entry_slip if not is_short else price - entry_slip
    
    total_cost = qty * execution_price
    
    if account.balance < total_cost:
        raise HTTPException(status_code=400, detail="Insufficient virtual balance")
    
    # Deduct balance
    account.balance -= total_cost
    
    # Create trade
    new_trade = PaperTrade(
        symbol=symbol,
        qty=qty,
        buy_price=execution_price,
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
    OPEN trades are enriched with current market prices.
    """
    result = await db.execute(select(PaperTrade).order_by(PaperTrade.buy_time.desc()))
    trades = result.scalars().all()
    
    open_symbols = [t.symbol for t in trades if t.status == "OPEN"]
    live_prices = {}
    if open_symbols:
        from app.services.kite_data import kite_data
        print(f"📊 [PAPER TRADES] Fetching live prices for {len(open_symbols)} positions. Kite ready: {kite_data.is_ready}")
        try:
            if kite_data.is_ready:
                live_prices = await kite_data.get_ltp(open_symbols)
                print(f"✅ [PAPER TRADES] Kite LTP returned {len(live_prices)} prices")
            else:
                # Eagerly attempt re-initialization (with timeout) so THIS request benefits
                if not getattr(kite_data, '_is_reconnecting', False):
                    kite_data._is_reconnecting = True
                    print("🔄 [PAPER TRADES] Kite not ready. Attempting eager re-init (15s timeout)...")
                    try:
                        await asyncio.wait_for(kite_data.initialize(), timeout=15.0)
                        if kite_data.is_ready:
                            live_prices = await kite_data.get_ltp(open_symbols)
                            print(f"✅ [PAPER TRADES] Kite re-init successful! Got {len(live_prices)} prices")
                        else:
                            print("⚠️ [PAPER TRADES] Kite re-init completed but still not ready")
                    except asyncio.TimeoutError:
                        print("⏱️ [PAPER TRADES] Kite re-init timed out (15s). Will retry next poll.")
                    except Exception as e:
                        print(f"⚠️ [PAPER TRADES] Kite re-init failed: {e}")
                    finally:
                        kite_data._is_reconnecting = False
                else:
                    print("⏳ [PAPER TRADES] Kite reconnect already in progress, using fallback")
        except Exception as e:
            print(f"⚠️ [PAPER TRADES] Kite LTP sync failed: {e}")

    # Enrich trades with live data (or fallbacks)
    enriched_trades = []
    for t in trades:
        try:
            trade_dict = {c.name: getattr(t, c.name) for c in t.__table__.columns}
            if t.status == "OPEN":
                # Use live price if available, else fallback to buy_price for stability
                price_info = live_prices.get(t.symbol) if live_prices else None
                current_price = t.buy_price
                is_live = False
                source = "FALLBACK"
                
                if price_info and isinstance(price_info, dict):
                    fetch_price = price_info.get("price", 0.0)
                    if fetch_price > 0:
                        current_price = fetch_price
                        is_live = True
                        source = price_info.get("source", "MARKET")
                
                trade_dict["current_price"] = current_price
                trade_dict["is_live"] = is_live
                trade_dict["price_source"] = source
                print(f"   💰 {t.symbol}: Buy={t.buy_price} → Live={current_price} ({source}) {'✅' if is_live else '⚠️ FALLBACK'}")
            enriched_trades.append(trade_dict)
        except Exception as e:
            print(f"⚠️ Error enriching trade {t.id}: {e}")
            enriched_trades.append({c.name: getattr(t, c.name) for c in t.__table__.columns})
        
    return sanitize_data(enriched_trades)

@router.patch("/close/{trade_id}")
async def close_paper_trade(trade_id: str, close_data: dict = Body(None), db: AsyncSession = Depends(get_db)):
    """
    Closes an open paper trade at the current market price.
    close_data can include 'reason' (SL, TARGET, EOD, MANUAL)
    """
    result = await db.execute(select(PaperTrade).where(PaperTrade.id == trade_id, PaperTrade.status == "OPEN"))
    trade = result.scalars().first()
    
    if not trade:
        raise HTTPException(status_code=404, detail="Open trade not found")
    
    # Get latest price (with fallback if market is throttled)
    try:
        current_price_data = await market_service.get_latest_price(trade.symbol)
        current_val = current_price_data.get("price", 0.0)
    except Exception:
        current_val = 0.0
        
    if not current_val:
        # Final Fallback: If YF is totally blocked, use the BUY PRICE as a fallback
        # to ensure the user can at least clear the position with zero loss/gain
        print(f"⚠️ Market data blocked for {trade.symbol}. Using fallback Buy Price.")
        current_val = trade.buy_price
    
    # Update trade
    trade.sell_price = current_val
    trade.sell_time = datetime.datetime.utcnow()
    trade.status = "CLOSED"
    trade.close_reason = close_data.get("reason", "MANUAL") if close_data else "MANUAL"
    
    # Update account balance and P&L
    account = await get_or_create_account(db)
    
    is_short_log = True if (trade.stop_loss and trade.buy_price and trade.stop_loss > trade.buy_price) else False
    if is_short_log:
        pnl = (trade.buy_price - current_val) * trade.qty
        proceeds = (trade.buy_price * trade.qty) + pnl
    else:
        proceeds = trade.qty * current_val
        pnl = proceeds - (trade.qty * trade.buy_price)
    
    account.balance += proceeds
    account.total_pnl += pnl
    
    await db.commit()
    return {"status": "closed", "sell_price": current_val, "pnl": pnl, "new_balance": account.balance}

@router.get("/history/daily")
async def get_daily_history(db: AsyncSession = Depends(get_db)):
    """
    Returns P&L history grouped by IST date to avoid UTC date-drift.
    """
    # Fetch all closed trades
    result = await db.execute(select(PaperTrade).where(PaperTrade.status == "CLOSED").order_by(PaperTrade.sell_time.desc()))
    trades = result.scalars().all()
    
    daily_stats = {}
    for t in trades:
        # Convert UTC sell_time to IST for correct calendar grouping
        ist_time = t.sell_time.replace(tzinfo=timezone.utc).astimezone(IST)
        date_str = ist_time.strftime("%Y-%m-%d")
        
        if date_str not in daily_stats:
            daily_stats[date_str] = {"pnl": 0.0, "trades_count": 0, "symbols": []}
        
        is_short_log = True if (t.stop_loss and t.buy_price and t.stop_loss > t.buy_price) else False
        
        if is_short_log:
            trade_pnl = (t.buy_price - t.sell_price) * t.qty
            pnl_percent = ((t.buy_price - t.sell_price) / t.buy_price) * 100 if t.buy_price else 0
        else:
            trade_pnl = (t.sell_price - t.buy_price) * t.qty
            pnl_percent = ((t.sell_price - t.buy_price) / t.buy_price) * 100 if t.buy_price else 0
        
        daily_stats[date_str]["pnl"] += trade_pnl
        daily_stats[date_str]["trades_count"] += 1
        daily_stats[date_str]["symbols"].append({
            "symbol": t.symbol,
            "buy_price": round(t.buy_price, 2),
            "sell_price": round(t.sell_price, 2),
            "pnl": round(trade_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
            "score": t.score_at_buy or 0,
            "reason": t.close_reason,
            "time": ist_time.strftime("%H:%M")
        })

    # Convert to list for frontend
    formatted_history = []
    # Sort dates descending
    sorted_dates = sorted(daily_stats.keys(), reverse=True)
    
    for date in sorted_dates:
        stats = daily_stats[date]
        formatted_history.append({
            "date": date,
            "total_pnl": round(stats["pnl"], 2),
            "count": stats["trades_count"],
            "details": stats["symbols"]
        })
        
    return sanitize_data(formatted_history)

@router.post("/reset_account")
async def reset_paper_trading(db: AsyncSession = Depends(get_db)):
    """
    Resets account balance and clears trade history.
    """
    account = await get_or_create_account(db)
    account.balance = 1000000.0
    account.total_pnl = 0.0
    
    await db.commit()
    return {"status": "reset", "balance": account.balance}
