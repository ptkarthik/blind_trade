import asyncio
import pandas as pd
import numpy as np
from app.services.ta_intraday import IntradayTechnicalAnalysis

async def test_reclaim_logic_mocked_v2():
    print("[TEST] Verifying Smart Gate Reclaim Logic (Mocked Data V2)...")
    
    # 1. Create Mock DataFrame (30 candles)
    # Drifting down from 100 to 90
    dates = pd.date_range("2024-01-01 09:15", periods=30, freq="15min")
    close_prices = np.linspace(100, 90, 30)
    df = pd.DataFrame({
        "open": close_prices,
        "high": close_prices + 0.5,
        "low": close_prices - 0.5,
        "close": close_prices,
        "volume": [1000] * 30
    }, index=dates)
    
    # Last Close is 90. EMA20 (window 20) will be around 95.
    # So trend_hold = False (Price 90 < EMA20 95)
    
    breakout_level = 85.0
    
    # Case A: No Smart Gate (Should have -50 penalty)
    res_no_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, breakout_level, context={"smart_gate": False})
    
    # Case B: Smart Gate (Should have -15 penalty)
    res_with_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, breakout_level, context={"smart_gate": True})
    
    # Note: Because the mock data is very poor, the base_score might be low/0.
    # To see the difference, we should look at the calculation or ensure base_score > 0.
    # Actually, we can just look at how the penalty is subtracted.
    
    score_a = res_no_gate.get('entry_score', 0)
    score_b = res_with_gate.get('entry_score', 0)
    
    print(f"Score NO Gate: {score_a}")
    print(f"Score WITH Gate: {score_b}")
    
    # If both are 0, we can't see the diff. Let's force a high base score by mocking 
    # more indicators (volume, trigger etc) if needed.
    # But wait, ta_intraday.py calculation:
    # entry_score = max(0, min(base_score - validation_penalty - trend_penalty, 100))
    
    # I'll modify the test to manually check the internal logic if needed, 
    # but let's try to make the base_score > 0.
    # I'll set some flags in the data to trigger pullback_score (30) and trigger_score (30).
    
    df.loc[df.index[-1], "low"] = 89.9 # Close to EMA9?
    df.loc[df.index[-1], "close"] = 91.0 # Bullish trigger
    df.loc[df.index[-1], "open"] = 90.0
    
    # Re-run
    res_no_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, 85.0, context={"smart_gate": False})
    res_with_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, 85.0, context={"smart_gate": True})
    
    print(f"RE-RUN -> Score NO Gate: {res_no_gate.get('entry_score')}")
    print(f"RE-RUN -> Score WITH Gate: {res_with_gate.get('entry_score')}")
    
    diff = res_with_gate.get('entry_score', 0) - res_no_gate.get('entry_score', 0)
    print(f"Difference: {diff} points")
    
    if diff > 0:
        print("SUCCESS: Smart Gate correctly changed the score result!")
    else:
        print(f"FAILURE: No difference detected. Check if trend_hold really failed.")

if __name__ == "__main__":
    asyncio.run(test_reclaim_logic_mocked_v2())
