import sys
import os
import asyncio
import pandas as pd
from datetime import datetime

# FORCE UTF-8 BEFORE ANY OTHER IMPORTS
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
from app.services.intraday_engine import intraday_engine
from app.services.market_data import market_service
from app.services.liquidity_service import liquidity_service

async def manual_test():
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ZOMATO.NS", "SUZLON.NS"]
    print(f"--- [PIONEER TEST] ---", flush=True)
    print(f"Testing Refined Engine Logic on: {symbols}", flush=True)
    
    await liquidity_service.initialize()
    # Mock some benchmarks if they don't exist to test the T.O.D logic
    # (In real run, liquidity_service would have them after bootstrap)
    
    index_ctx = await intraday_engine._get_index_context()
    print(f"Market Context: {index_ctx.get('market_regime')} (Sideways: {index_ctx.get('is_sideways')})", flush=True)
    
    try:
        res_15m, res_1h, res_prices = await asyncio.wait_for(
            asyncio.gather(
                market_service.get_batch_ohlc(symbols, interval="15m", period="7d"),
                market_service.get_batch_ohlc(symbols, interval="60m", period="15d"),
                market_service.get_batch_prices(symbols)
            ),
            timeout=120.0
        )
    except Exception as e:
        print(f"❌ Batch Fetching failed: {e}", flush=True)
        return
        
    batch_pulse = {}
    for s in symbols:
        batch_pulse[s] = {"15m": res_15m.get(s), "1h": res_1h.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}

    for sym in symbols:
        print(f"\n--- Checking {sym} ---", flush=True)
        res = await intraday_engine.analyze_stock(sym, "TEST_JOB", index_ctx, batch_pulse)
        if "skip_reason" in res:
             print(f"⏭️ {sym}: Skipped ({res['skip_reason']})", flush=True)
        else:
             print(f"Result for {sym}:", flush=True)
             print(f"  Score: {res['score']} | {res['signal']} | {res.get('alpha_mode')}", flush=True)
             print(f"  L1/L2/L3 Breakdown: L1:{res['groups']['DNA (40%)']['score']} | L2:{res['groups']['Alpha Edge (60%)']['score']} | L3:{res['groups']['Safeguards (L3)']['score']}", flush=True)
             
             print("  Reasons:", flush=True)
             for r in res.get('reasons', []):
                 impact_str = f"[{r['impact']}]" if 'impact' in r else ""
                 print(f"    - {r['text']} {impact_str}", flush=True)

if __name__ == "__main__":
    asyncio.run(manual_test())
