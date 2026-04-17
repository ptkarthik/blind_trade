import asyncio
import pandas as pd
import numpy as np
from app.services.ta_intraday import IntradayTechnicalAnalysis

async def test_reclaim_logic_mocked():
    print("[TEST] Verifying Smart Gate Reclaim Logic (Mocked Data)...")
    
    # 1. Create Mock DataFrame (25 candles)
    dates = pd.date_range("2024-01-01 09:15", periods=30, freq="15min")
    df = pd.DataFrame({
        "open": np.linspace(100, 95, 30),
        "high": np.linspace(101, 96, 30),
        "low": np.linspace(99, 94, 30),
        "close": np.linspace(100, 95, 30),
        "volume": [1000] * 30
    }, index=dates)
    
    # Scenario: Price is 95, EMA20 is 97.5 (calculated over 20 candles of 100->95)
    # Price is BELOW EMA20.
    
    # Add a "Reclaim" candle at the end
    df.loc[df.index[-1], "close"] = 98 # Pop above EMA20 (97.5) or just a strong move
    df.loc[df.index[-1], "low"] = 97.8
    df.loc[df.index[-1], "high"] = 98.5
    
    # Force indicators to look like a reclaim
    # We'll just test the context bypass
    
    breakout_level = 96.0
    
    # Case A: No Smart Gate (Should have -50 penalty)
    res_no_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, breakout_level, context={"smart_gate": False})
    
    # Case B: Smart Gate (Should have -15 penalty)
    res_with_gate = IntradayTechnicalAnalysis.detect_pullback_entry_v45(df, breakout_level, context={"smart_gate": True})
    
    print(f"Score NO Gate: {res_no_gate.get('entry_score')}")
    print(f"Score WITH Gate: {res_with_gate.get('entry_score')}")
    
    diff = res_with_gate.get('entry_score', 0) - res_no_gate.get('entry_score', 0)
    print(f"Difference: {diff} points")
    
    if diff >= 35: # 50 - 15 = 35 points difference
        print("SUCCESS: Smart Gate correctly waived 35 points of the trend penalty!")
    else:
        print(f"FAILURE: Expected ~35 point difference, got {diff}")

if __name__ == "__main__":
    asyncio.run(test_reclaim_logic_mocked())
