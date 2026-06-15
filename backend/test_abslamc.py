import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')
from app.services.swing_engine import SwingEngine
from app.services.market_data import market_service

async def test():
    await market_service.initialize()
    engine = SwingEngine()
    
    sym = "ABSLAMC.NS"
    try:
        res = await engine.analyze_stock(sym)
        if res:
            print(f"[{sym}] SCORE: {res.get('score')} | SIGNAL: {res.get('signal')} | VERDICT: {res.get('strategic_summary')}")
            print("REASONS:")
            for r in res.get('reasons', []):
                print(f"  - {r.get('type')}: {r.get('text')} (Layer {r.get('layer')} | Impact: {r.get('impact')})")
        else:
            print(f"[{sym}] RETURNED NONE (Filtered out)")
    except Exception as e:
        print(f"[{sym}] ERROR: {e}")

asyncio.run(test())
