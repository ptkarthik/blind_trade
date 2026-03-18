import pandas as pd
import numpy as np
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.ta_intraday import IntradayTechnicalAnalysis

def test_trend_guard_v6_2():
    print("\n--- Testing Trend Direction Guard (V6.2) ---")
    
    # Setup 1: Bearish Alignment (EMA 20 < EMA 50)
    # Price trending down
    prices = [100 - i/10 for i in range(100)]
    df_bearish = pd.DataFrame({'close': prices})
    
    res_bearish = IntradayTechnicalAnalysis.detect_trend_direction(df_bearish)
    print(f"Bearish Trend: {res_bearish['trend_direction_state']}, EMA20: {res_bearish.get('ema_20')}, EMA50: {res_bearish.get('ema_50')}")
    assert res_bearish['trend_direction_state'] == 'BEARISH_TREND'
    assert res_bearish['ema_alignment'] == False
    
    # Setup 2: Bullish Alignment + Positive Slope
    prices_bull = [100 + i/10 for i in range(100)]
    df_bullish = pd.DataFrame({'close': prices_bull})
    
    res_bullish = IntradayTechnicalAnalysis.detect_trend_direction(df_bullish)
    print(f"Bullish Trend: {res_bullish['trend_direction_state']}, EMA20: {res_bullish.get('ema_20')}, EMA50: {res_bullish.get('ema_50')}, Slope: {res_bullish.get('slope_20')}")
    assert res_bullish['trend_direction_state'] == 'BULLISH_TREND'
    assert res_bullish['ema_alignment'] == True
    
    # Setup 3: Bullish Alignment + Flat/Neutral Slope
    prices_neutral = [100 + i/5 for i in range(70)] + [114.0] * 30
    df_neutral = pd.DataFrame({'close': prices_neutral})
    
    res_neutral = IntradayTechnicalAnalysis.detect_trend_direction(df_neutral)
    print(f"Neutral Trend: {res_neutral['trend_direction_state']}, EMA20: {res_neutral.get('ema_20')}, EMA50: {res_neutral.get('ema_50')}, Slope: {res_neutral.get('slope_20')}")
    assert res_neutral['trend_direction_state'] == 'NEUTRAL_TREND'
    assert res_neutral['ema_alignment'] == True
    
    print("Trend Direction Guard V6.2 Logic: SUCCESS")

if __name__ == "__main__":
    try:
        test_trend_guard_v6_2()
        print("\nSUCCESS: V6.2 TREND GUARD VERIFIED.")
    except Exception as e:
        print(f"\nFAILURE: VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
