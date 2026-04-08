
import asyncio
import os
import sys
import datetime
from unittest.mock import AsyncMock, patch

# Trace Path to find backend/app
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.db.session import AsyncSessionLocal
from app.models.papertrade import PaperTrade, Account
from app.services.paper_monitor import paper_monitor
from sqlalchemy import select, delete

async def verify_automation():
    print("--- 🛰️ Starting FAST Automation Verification (Mocked) ---")
    
    # 1. Setup Data
    async with AsyncSessionLocal() as session:
        await session.execute(delete(PaperTrade))
        acc_res = await session.execute(select(Account).limit(1))
        account = acc_res.scalars().first()
        if not account:
            account = Account(balance=1000000.0)
            session.add(account)
        else:
            account.balance = 1000000.0
            account.total_pnl = 0.0
        
        # Test Case 1: Target Hit (Price: 3000, Target: 2100)
        t1 = PaperTrade(id="hit-target", symbol="REL_TEST", qty=10, buy_price=2000, target=2100, status="OPEN", product_type="MIS")
        
        # Test Case 2: SL Hit (Price: 3000, SL: 3500)
        t2 = PaperTrade(id="hit-sl", symbol="TCS_TEST", qty=1, buy_price=4000, stop_loss=3500, status="OPEN", product_type="MIS")
        
        # Test Case 3: EOD Exit (MIS only)
        t3 = PaperTrade(id="hit-eod", symbol="INFY_TEST", qty=10, buy_price=1000, status="OPEN", product_type="MIS")
        
        session.add(t1)
        session.add(t2)
        session.add(t3)
        await session.commit()

    # 2. Mock the Market Data & Clock
    async def mock_price(sym):
        return {"price": 3000.0}

    # We mock 'datetime.utcnow' to simulate 3:19 PM IST (09:49 UTC)
    mock_now = datetime.datetime(2026, 4, 5, 10, 0, 0) # 10:00 UTC > 09:48 UTC (3:18 PM IST)

    with patch('app.services.paper_monitor.market_service.get_latest_price', side_effect=mock_price), \
         patch('app.services.paper_monitor.datetime') as mock_dt:
        
        mock_dt.utcnow.return_value = mock_now
        
        print("🔄 Running PaperMonitor.check_trades() Pulse...")
        await paper_monitor.check_trades()
    
    # 3. Verify Final State
    async with AsyncSessionLocal() as session:
        r1 = await session.get(PaperTrade, "hit-target")
        r2 = await session.get(PaperTrade, "hit-sl")
        r3 = await session.get(PaperTrade, "hit-eod")
        
        results = []
        if r1 and r1.status == "CLOSED" and r1.close_reason == "TARGET":
            results.append("🎯 TARGET: Success")
        else:
            results.append(f"❌ TARGET: Fail ({r1.status if r1 else 'None'}, {r1.close_reason if r1 else 'None'})")

        if r2 and r2.status == "CLOSED" and r2.close_reason == "STOP_LOSS":
            results.append("🚨 SL: Success")
        else:
            results.append(f"❌ SL: Fail ({r2.status if r2 else 'None'}, {r2.close_reason if r2 else 'None'})")

        if r3 and r3.status == "CLOSED" and r3.close_reason == "EOD":
            results.append("🕒 EOD: Success")
        else:
            results.append(f"❌ EOD: Fail ({r3.status if r3 else 'None'}, {r3.close_reason if r3 else 'None'})")

        print("\n".join(results))

        # 4. Check Daily History
        from app.api.api_v1.endpoints.papertrades import get_daily_history
        history = await get_daily_history(session)
        print(f"📊 Daily Stats: {len(history)} days found.")
        if len(history) > 0:
             print(f"✅ Daily History verification passed. P&L: {history[0]['total_pnl']}")
        else:
             print(f"❌ Daily History verification failed.")

if __name__ == "__main__":
    asyncio.run(verify_automation())
