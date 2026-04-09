import sys
import os
import pandas as pd
import numpy as np
import asyncio

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import IntradayEngine

async def verify_alpha_archetypes():
    engine = IntradayEngine()
    engine.SCORING_FLAGS["enable_dynamic_alpha"] = True
    engine.SCORING_FLAGS["debug_alpha_mode"] = True
    
    # helper to mock df
    def get_mock_df(price_start=100.0, price_end=115.0, vol=1.0):
        dates = pd.date_range("2026-04-09 09:15", periods=30, freq="5min")
        step = (price_end - price_start) / 30
        close = [price_start + i*step for i in range(30)]
            
        return pd.DataFrame({
            "open": [c - 0.1 for c in close],
            "high": [c + 0.1 for c in close],
            "low": [c - 0.05 for c in close], # Strong uptrend
            "close": close,
            "volume": [1000 * vol] * 30
        }, index=dates)

    # 1. Test EARLY (Force near VWAP by having price hover at start)
    print("--- Test Archetype: EARLY ---")
    # Low price movement initially, then small breakout
    df_early = get_mock_df(100, 101, vol=2.0) 
    res_early = await engine.analyze_stock("EARLY", pulse_data={"EARLY": df_early})
    print(f"Alpha Mode: {res_early.get('alpha_mode')} | L1: {res_early['groups']['DNA (40%)']['score']} | L2: {res_early['groups']['Alpha Edge (60%)']['score']}")
    
    # 2. Test MOMENTUM (High price end, Vol > 2.0)
    print("\n--- Test Archetype: MOMENTUM ---")
    df_mom = get_mock_df(100, 130, vol=3.0) # 30% hike, far from vwap
    res_mom = await engine.analyze_stock("MOM", pulse_data={"MOM": df_mom})
    print(f"Alpha Mode: {res_mom.get('alpha_mode')} | L1: {res_mom['groups']['DNA (40%)']['score']} | L2: {res_mom['groups']['Alpha Edge (60%)']['score']}")

    # 3. Test DNA Safety Gate (L1 < 20)
    print("\n--- Test DNA Safety Gate ---")
    df_weak = get_mock_df(100, 102, vol=0.2) # Low volume should drop DNA
    res_weak = await engine.analyze_stock("WEAK", pulse_data={"WEAK": df_weak})
    print(f"L1 Score: {res_weak['groups']['DNA (40%)']['score']} | Alpha Mode: {res_weak.get('alpha_mode')}")
    if res_weak.get('alpha_mode') == "NONE":
        print("✅ Safety Gate Passed (Logic forced NONE due to L1 < 20)")
    
    # 4. Backward Compatibility Check
    print("\n--- Test Backward Compatibility (Flag OFF) ---")
    engine.SCORING_FLAGS["enable_dynamic_alpha"] = False
    res_off = await engine.analyze_stock("MOM", pulse_data={"MOM": df_mom})
    print(f"Alpha Mode (Expected None): {res_off.get('alpha_mode')} | L2 Score: {res_off['groups']['Alpha Edge (60%)']['score']}")

if __name__ == "__main__":
    asyncio.run(verify_alpha_archetypes())
