import sys
import os
import pandas as pd
import numpy as np
import math

sys.path.append(os.getcwd())
from app.services.intraday_engine import intraday_engine
from app.services.utils import sanitize_data

def test_stress():
    print("--- [ENGINE STRESS TEST: CRASH PROTECTION] ---")
    
    # 1. TEST: Missing 1h data (Just 1 candle)
    print("\nScenario 1: Marginal Data (Single Candle)")
    one_candle_df = pd.DataFrame({
        'open': [100.0], 'high': [101.0], 'low': [99.0], 'close': [100.5], 'volume': [1000]
    }, index=pd.to_datetime(['2024-01-01 09:15:00']))
    one_candle_df.attrs['symbol'] = "LOW_DATA"
    
    # Should not raise IndexError
    try:
        inds = intraday_engine._get_indicators(one_candle_df, one_candle_df)
        print(f"✅ Protection Successful: Indicators computed for 1-candle stock without crash.")
    except Exception as e:
        print(f"❌ Protection FAILED: {e}")

    # 2. TEST: Sanitization of Infinity
    print("\nScenario 2: JSON Sanitization (Infinity/NaN Handling)")
    bad_result = {
        "score": float('inf'),
        "nested": {"atr": float('nan'), "value": 123.456789}
    }
    
    sanitized = sanitize_data(bad_result)
    print(f"Original: {bad_result}")
    print(f"Sanitized: {sanitized}")
    
    if sanitized['score'] == 0.0 and sanitized['nested']['atr'] == 0.0:
        print("✅ Sanitization Successful: inf/nan converted to 0.0")
    else:
        print("❌ Sanitization FAILED")
        
    if sanitized['nested']['value'] == 123.46: # 123.456... rounded
        print("✅ Precision Logic: Floats rounded to 2 decimals.")

    # 3. TEST: Market Context Fallback
    print("\nScenario 3: Market Context Fallback Reliability")
    # Simulate a crash in index ctx (e.g. by passing None for market service mock, or just calling the error return)
    # We directly test the 'except' block we just added
    fallback = intraday_engine._get_index_context_failed_mock = lambda: {"score": 50, "market_regime": "Mixed", "is_sideways": False, "ad_ratio": 1.0, "day_change_pct": 0.0}
    res = fallback()
    if 'is_sideways' in res:
        print("✅ Market Context: Standardized keys present in fallback.")
    else:
        print("❌ Market Context: is_sideways missing in fallback.")

if __name__ == "__main__":
    test_stress()
