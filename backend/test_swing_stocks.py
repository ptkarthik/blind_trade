import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.services.swing_engine import SwingEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = SwingEngine()
    
    # We will test the stocks the user mentioned
    stocks = [
        "CANFINHOME.NS", "IDFCFIRSTB.NS", "ACE.NS", "RAJRATAN.NS", "RKFORGE.NS", "PITTIENG.NS",
        "GRINDWELL.NS", "MANINFRA.NS", "PRAKASH.NS", "SILVERTUC.NS", "AEGISCHEM.NS", "AURIONPRO.NS",
        "STALLION.NS", "BLUEDART.NS"
    ]
    
    for sym in stocks:
        try:
            res = await engine.analyze_stock(sym)
            if res:
                print(f"[{sym}] SCORE: {res.get('score')} | SIGNAL: {res.get('signal')} | VERDICT: {res.get('strategic_summary')}")
                print(f"    -> Top Reasons: {res.get('reasons', [])[:2]}")
            else:
                print(f"[{sym}] RETURNED NONE (Filtered out completely)")
        except Exception as e:
            print(f"[{sym}] ERROR: {e}")

asyncio.run(test())
