import sys
import os
import pandas as pd
import numpy as np
import asyncio
from datetime import datetime
import pytz

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import IntradayEngine

async def verify_logic():
    engine = IntradayEngine()
    
    # Mock some data (Trending stock)
    # price > vwap, price > ema20, ema20 rising, vol > 2.0
    dates = pd.date_range("2026-04-09 09:15", periods=30, freq="5min")
    df = pd.DataFrame({
        "open": [100 + i*0.5 for i in range(30)],
        "high": [100.5 + i*0.5 for i in range(30)],
        "low": [99.5 + i*0.5 for i in range(30)],
        "close": [101.0 + i*0.5 for i in range(30)],
        "volume": [1000] * 30
    }, index=dates)
    
    # IntradayEngine expects pulse_data to be a dict where sym maps to a DataFrame or dict
    pulse_data = {"TEST": df}
    
    # 1. Test Flags OFF (Backward Compatibility)
    print("--- Test Flags OFF ---")
    engine.SCORING_FLAGS["enable_momentum_leader"] = False
    engine.SCORING_FLAGS["enable_extended_structure"] = False
    
    res_off = await engine.analyze_stock("TEST", pulse_data=pulse_data)
    l2_off = res_off["groups"]["Alpha Edge (60%)"]["score"]
    print(f"L2 Score (OFF): {l2_off}")
    
    # 2. Test Flags ON (New Functionality)
    print("\n--- Test Flags ON ---")
    engine.SCORING_FLAGS["enable_momentum_leader"] = True
    engine.SCORING_FLAGS["enable_extended_structure"] = True
    
    res_on = await engine.analyze_stock("TEST", pulse_data=pulse_data)
    l2_on = res_on["groups"]["Alpha Edge (60%)"]["score"]
    print(f"L2 Score (ON): {l2_on}")
    
    reasons = res_on.get("reasons", [])
    mom_reason = [r for r in reasons if "Momentum Leader" in r["text"]]
    if mom_reason:
        print(f"PASS: Found Momentum Leader Reason: {mom_reason[0]}")
    else:
        print("FAIL: Momentum Leader NOT found (check trend conditions)")

if __name__ == "__main__":
    asyncio.run(verify_logic())
