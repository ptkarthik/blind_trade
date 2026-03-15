import pandas as pd
import numpy as np
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# In-line mock of components if needed, but we try to import just the TA class
from app.services.ta_intraday import IntradayTechnicalAnalysis

def test_failed_breakout():
    print("\n--- Testing Failed Breakout (V5) ---")
    # Base level 100
    # Candle -3: Close 102 (Breakout)
    # Candle -2: Close 101
    # Candle -1: Close 99 (Failed)
    data = {
        'open':  [99]*27 + [100, 102, 101],
        'high':  [100]*27 + [101, 103, 102],
        'low':   [98]*27  + [99, 101, 98.5],
        'close': [99]*27  + [100.5, 102, 99.5], 
        'volume':[1000]*30
    }
    df = pd.DataFrame(data)
    df.index = pd.date_range(start="2026-03-15 09:15", periods=30, freq="5min")
    
    # We need to ensure a breakout level is identified. 
    # PDH setup in previous days
    prev_data = {
        'high': [100]*10, 'low': [98]*10, 'close': [99]*10, 'volume': [500]*10
    }
    df_prev = pd.DataFrame(prev_data)
    df_prev.index = pd.date_range(start="2026-03-14 09:15", periods=10, freq="5min")
    
    full_df = pd.concat([df_prev, df])
    
    # breakout_level should be 100 (PDH)
    res = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(full_df)
    print(f"Breakout Level: {res.get('breakout_level')}")
    print(f"Fake Breakout Flag: {res.get('fake_breakout_flag')}")
    print(f"Breakout Strength: {res.get('breakout_strength')}")
    
    # Latest close is 99.5, prev close was 102 (above 100).
    assert res.get('fake_breakout_flag') == True
    print("Test Passed: Failed Breakout detected.")

def test_market_structure():
    print("\n--- Testing Market Structure (V5) ---")
    
    # Bullish: HH + HL
    df_bull = pd.DataFrame({
        'high': [100, 101],
        'low': [99, 99.5],
        'close': [100, 101]
    })
    res_bull = IntradayTechnicalAnalysis.detect_market_structure(df_bull)
    print(f"Bullish State: {res_bull.get('market_structure_state')}")
    assert res_bull.get('market_structure_state') == "BULLISH_STRUCTURE"
    
    # Bearish: LH
    df_bear = pd.DataFrame({
        'high': [101, 100.5],
        'low': [99, 99.2],
        'close': [100, 100]
    })
    res_bear = IntradayTechnicalAnalysis.detect_market_structure(df_bear)
    print(f"Bearish State: {res_bear.get('market_structure_state')}")
    assert res_bear.get('market_structure_state') == "BEARISH_STRUCTURE"
    
    print("Test Passed: Market Structure validated.")

if __name__ == "__main__":
    try:
        test_failed_breakout()
        test_market_structure()
        print("\n✅ SPECIALIST V5 TA LOGIC VERIFIED.")
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
