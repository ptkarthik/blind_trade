import pandas as pd
import numpy as np
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.ta_intraday import IntradayTechnicalAnalysis
from app.services.ta_swing import SwingTechnicalAnalysis
from app.services.ta_longterm import LongTermTechnicalAnalysis

def test_duplicate_columns():
    print("\n--- Testing Duplicate Column Handling ---")
    
    # Create a DataFrame with duplicate 'close' columns
    data = {
        'open': [100, 101, 102, 103, 104, 105],
        'high': [110, 111, 112, 113, 114, 115],
        'low': [90, 91, 92, 93, 94, 95],
        'close': [105, 106, 107, 108, 109, 110],
        'volume': [1000, 1100, 1200, 1300, 1400, 1500]
    }
    df = pd.DataFrame(data)
    
    # Force duplicate columns
    df = pd.concat([df, df['close'].rename('close')], axis=1)
    df = pd.concat([df, df['high'].rename('high')], axis=1)
    df = pd.concat([df, df['low'].rename('low')], axis=1)
    df = pd.concat([df, df['volume'].rename('volume')], axis=1)
    
    print(f"DataFrame columns: {list(df.columns)}")
    print(f"Is 'close' duplicate? {sum(df.columns == 'close') > 1}")

    # Test 1: Intraday Market Structure
    print("\nTesting ta_intraday.detect_market_structure...")
    try:
        res = IntradayTechnicalAnalysis.detect_market_structure(df)
        print(f"SUCCESS: Market Structure state: {res['market_structure_state']}")
    except Exception as e:
        print(f"FAILURE: detect_market_structure failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Intraday Liquidity Trap
    print("\nTesting ta_intraday.detect_liquidity_trap...")
    try:
        res = IntradayTechnicalAnalysis.detect_liquidity_trap(df)
        print(f"SUCCESS: Trap detected: {res['trap_move_detected']}")
    except Exception as e:
        print(f"FAILURE: detect_liquidity_trap failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Swing Analysis
    # Needs 200 rows for Swing
    df_long = pd.concat([df] * 40, ignore_index=True)
    print("\nTesting ta_swing.analyze_swing (with 240 rows)...")
    try:
        res = SwingTechnicalAnalysis.analyze_swing(df_long)
        print(f"SUCCESS: Swing result match: {res['match']}")
    except Exception as e:
        print(f"FAILURE: analyze_swing failed: {e}")
        import traceback
        traceback.print_exc()

    # Test 4: Longterm Analysis
    # Needs 50 rows
    df_med = pd.concat([df] * 10, ignore_index=True)
    print("\nTesting ta_longterm.analyze_stock (with 60 rows)...")
    try:
        res = LongTermTechnicalAnalysis.analyze_stock(df_med)
        print(f"SUCCESS: Longterm score: {res.get('score', 'N/A')}")
    except Exception as e:
        print(f"FAILURE: analyze_stock failed: {e}")
        import traceback
        traceback.print_exc()
        import traceback
        traceback.print_exc()

    # Test 5: Intraday Smart Money Accumulation
    print("\nTesting ta_intraday.detect_smart_money_accumulation...")
    try:
        res = IntradayTechnicalAnalysis.detect_smart_money_accumulation(df_med)
        print(f"SUCCESS: Accumulation detected: {res['accumulation_detected']}")
    except Exception as e:
        print(f"FAILURE: detect_smart_money_accumulation failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_duplicate_columns()
