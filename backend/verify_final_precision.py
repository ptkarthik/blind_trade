import pandas as pd
import numpy as np
import sys
import os

# Add project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import app.services.ta_intraday as ta_intraday

def test_final_precision():
    print("--- Testing Final Precision Refinements (V6.3) ---")
    
    # 1. Mock Data for Trap Detection (10-candle windows)
    # 20 candles total
    data = {
        'open': [100.0] * 20,
        'high': [101.0] * 20,
        'low': [99.0] * 20,
        'close': [100.0] * 20,
        'volume': [1000.0] * 20
    }
    
    # Trigger a trap on the last candle
    # Conditions:
    # 1. vol_spike_ratio > 1.8 (ma10 of 1000 is 1000, so need > 1800)
    # 2. upper_wick > 50%
    # 3. close_position <= 0.30
    # 4. range_expansion_ratio >= 1.7 (ma10 range is 2, so need > 3.4)
    
    data['high'][19] = 110.0
    data['low'][19] = 100.0
    data['close'][19] = 101.0 # close_pos = (101-100)/(110-100) = 0.1 (OK)
    data['open'][19] = 101.0
    data['volume'][19] = 3000.0 # vol_spike = 3000/1000 = 3.0 (OK)
    
    df = pd.DataFrame(data)
    df.index = pd.date_range("2024-01-01 09:15", periods=len(df), freq="15min")
    
    # range = 10. ma10 range was 2. expansion = 5.0 (OK)
    
    trap_res = ta_intraday.IntradayTechnicalAnalysis.detect_liquidity_trap(df)
    
    print(f"Trap Detected: {trap_res.get('trap_move_detected')}")
    if 'details' in trap_res:
        print(f"Trap Details: {trap_res['details']}")
    else:
        print("⚠️ Trap Details MISSING from response.")
    
    # 2. Test RVOL Fallback (divisor = 25)
    # Mocking ta_intraday to use a symbol that lacks benchmark
    df.attrs['symbol'] = "NEW_STOCK"
    
    # Mock liquidity_service return
    class MockLiq:
        def get_liquidity(self, s): return {"adv20": 250000}
        def get_benchmark_vol(self, s, t): return 0
    
    ta_intraday.liquidity_service = MockLiq()
    
    res = ta_intraday.IntradayTechnicalAnalysis.analyze_stock(df)
    # Expected RVOL = 3000 / (250000 / 25) = 3000 / 10000 = 0.3
    rvol_val = res.get('rvol_val')
    print(f"RVOL Val (Fallback): {rvol_val}")
    print(f"RVOL Reference: {res.get('rvol_time_reference')}")

    success = True
    if not trap_res.get('trap_move_detected'):
        print("❌ FAILED: Trap not detected as expected.")
        success = False
    if rvol_val != 0.3:
        print(f"❌ FAILED: RVOL Fallback logic mismatch. Expected 0.3, got {rvol_val}")
        success = False

    if success:
        print("\nSUCCESS: All Final Precision Formulations Verified.")
    else:
        print("\nFAILURE: Precision logic mismatch.")

if __name__ == "__main__":
    test_final_precision()
