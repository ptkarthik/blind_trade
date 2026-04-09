import sys
import os
import pandas as pd
import numpy as np
import asyncio

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import IntradayEngine

async def verify_dynamic_dna():
    engine = IntradayEngine()
    
    # Mock some data (Trending stock)
    # price > vwap, price > ema20, ema20 rising, vol > 2.0, dist > 1.2%
    dates = pd.date_range("2026-04-09 09:15", periods=30, freq="5min")
    df = pd.DataFrame({
        "open": [100 + i*0.5 for i in range(30)],
        "high": [100.5 + i*0.5 for i in range(30)],
        "low": [99.5 + i*0.5 for i in range(30)],
        "close": [101.0 + i*0.5 for i in range(30)],
        "volume": [1000] * 30
    }, index=dates)
    
    pulse_data = {"TEST": df}
    
    # 1. Test Flags OFF (Backward Compatibility)
    print("--- Test Dynamic DNA OFF ---")
    engine.SCORING_FLAGS["enable_dynamic_dna"] = False
    
    res_off = await engine.analyze_stock("TEST", pulse_data=pulse_data)
    if "groups" not in res_off:
        print(f"OFF Mode Skip/Error: {res_off}")
        return
        
    l1_off = res_off["groups"]["DNA (40%)"]["score"]
    print(f"L1 Score (OFF): {l1_off}")
    
    # 2. Test Flags ON (Relaxed Mode)
    print("\n--- Test Dynamic DNA ON (RELAXED) ---")
    engine.SCORING_FLAGS["enable_dynamic_dna"] = True
    engine.SCORING_FLAGS["debug_dna_mode"] = True
    
    res_on = await engine.analyze_stock("TEST", pulse_data=pulse_data)
    if "groups" not in res_on:
        print(f"ON Mode Skip/Error: {res_on}")
        return
        
    l1_on = res_on["groups"]["DNA (40%)"]["score"]
    print(f"L1 Score (ON): {l1_on}")
    print(f"DNA Mode Detected: {res_on.get('dna_mode')}")
    
    if l1_on < l1_off:
        print("PASS: Dynamic DNA correctly scaled down Layer 1 score in RELAXED mode.")
    else:
        print("FAIL: L1 score did not reduce (check trend conditions)")

if __name__ == "__main__":
    asyncio.run(verify_dynamic_dna())
