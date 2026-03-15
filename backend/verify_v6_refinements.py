import pandas as pd
import numpy as np
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.ta_intraday import IntradayTechnicalAnalysis

def test_trap_logic_v6_1():
    print("\n--- Testing Liquidity Trap Rejection Filter (V6.1) ---")
    
    # 5 Conditions: Range, Wick, Vol, Re-entry, Bottom 30% close
    # Setup Trap: Condition 1 (Range), 2 (Wick), 3 (Vol), 4 (Re-entry), 5 (Bottom 30% close)
    # Body: 100 to 101 (1.0)
    # High: 105 (Wick = 4.0) -> > 50% of body
    # Close: 100.5 (Bottom 30% of 99.5 to 105 range is <= 101.15)
    # Range: 5.5 (Prev avg 1.0)
    # Volume: 5000 (Prev avg 1000)
    
    data = {
        'open':  [100]*19 + [100],
        'high':  [101]*19 + [105],
        'low':   [99.5]*19 + [99.5],
        'close': [100.2]*19 + [100.5], # Close at 100.5 is in bottom 20% of 99.5-105
        'volume':[1000]*19 + [5000]
    }
    df = pd.DataFrame(data)
    
    res = IntradayTechnicalAnalysis.detect_liquidity_trap(df)
    print(f"Trap Detected: {res.get('trap_move_detected')}")
    print(f"Conditions Count: {res.get('conditions_count')}")
    print(f"Details: {res.get('details')}")
    
    # Verify that it detects even with 5 conditions now (it needs 4/5)
    assert res.get('trap_move_detected') == True
    assert res.get('conditions_count') >= 4
    assert res.get('details').get('bottom_30_close') == True
    print("Liquidity Trap V6.1 Logic: SUCCESS")

def test_accumulation_duration():
    print("\n--- Testing Accumulation Duration Fix (V6.1) ---")
    
    # Baseline data (not consolidating)
    data = {
        'open':  [100.0]*30,
        'high':  [110.0]*30, # Range large
        'low':   [90.0]*30,
        'close': [100.0]*30,
        'volume':[1000.0]*30
    }
    # Last 3 candles tight
    for i in range(27, 30):
        data['high'][i] = 100.5
        data['low'][i] = 99.5
    
    df = pd.DataFrame(data)
    res = IntradayTechnicalAnalysis.detect_smart_money_accumulation(df)
    print(f"Short Accumulation Detected: {res.get('accumulation_detected')}")
    # Should be False because duration_validation (4 bars) fails
    assert res.get('accumulation_detected') == False
    
    print("Accumulation Duration Logic: SUCCESS (Blocked < 4 bars)")

if __name__ == "__main__":
    try:
        test_trap_logic_v6_1()
        test_accumulation_duration()
        print("\nSUCCESS: V6.1 TA REFINEMENTS VERIFIED.")
    except Exception as e:
        print(f"\nFAILURE: VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
