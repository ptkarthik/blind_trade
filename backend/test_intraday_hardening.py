import asyncio
import pandas as pd
import numpy as np
from app.services.ta_intraday import IntradayTechnicalAnalysis
from app.services.intraday_engine import intraday_engine
from app.services.market_data import market_service
import json

async def test_reclaim_logic():
    print("[TEST] Verifying Smart Gate Reclaim Logic (Below EMA20)...")
    
    symbol = "RELIANCE.NS"
    df = await market_service.get_ohlc(symbol, period="3d", interval="15m")
    if df.empty:
        print("Could not fetch real data for test.")
        return

    latest_idx = df.index[-1]
    last_close = df['close'].iloc[-1]
    
    context = {
        "smart_gate": True,
        "vol_mult": 1.0
    }
    
    print(f"--- Testing ta_intraday.detect_pullback_entry_v45 with context={context} ---")
    res = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, last_close, context=context)
    
    print(f"Result Score: {res.get('entry_score')}")
    print(f"Quality: {res.get('entry_quality')}")
    print(f"Is Entry: {res.get('is_entry')}")
    
    if res.get('entry_score', 0) > 60:
        print("SUCCESS: Smart Gate bypass allowed a high score despite being (presumably) complex.")
    else:
        print("Result score low. This might be due to other indicators in real data.")

async def test_engine_integration():
    print("\n[TEST] Verifying Engine Integration (Batch Delay & Context)...")
    
    symbol = "TCS.NS"
    print(f"Analyzing {symbol} through engine...")
    
    try:
        res = await intraday_engine.analyze_stock(symbol, "test_job")
        if res:
            print(f"Engine Score: {res.get('score')}")
            print(f"Alpha Mode: {res.get('mode')}")
            l2_score = res.get("groups", {}).get("Alpha Edge (60%)", {}).get("score", 0)
            print(f"L2 Score: {l2_score}")
    except Exception as e:
        print(f"Engine Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_reclaim_logic())
    asyncio.run(test_engine_integration())
