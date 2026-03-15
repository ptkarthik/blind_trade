import pandas as pd
import numpy as np
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mock services
import types
m_ctx = types.ModuleType('app.services.index_context')
m_ctx.index_ctx = {"market_regime": "Mixed", "ad_ratio": 1.0, "market_trend": "Neutral", "score": 50}
sys.modules['app.services.index_context'] = m_ctx

m_market = types.ModuleType('app.services.market_data')
m_market.market_service = types.SimpleNamespace(
    get_sector_for_symbol=lambda x: "IT",
    get_ohlc=lambda *args, **kwargs: pd.DataFrame(),
    get_latest_price=lambda x: 100.0
)
sys.modules['app.services.market_data'] = m_market

from app.services.ta_intraday import IntradayTechnicalAnalysis

def test_breakout_hold_validation():
    print("\n--- Testing Breakout Hold Validation (V6.3 Refinement) ---")
    
    # Need at least 30 candles
    # swing_high will be calculated from df['high'].iloc[-5:-1] which is indices [25, 26, 27, 28]
    data = {
        'high': [90] * 25 + [95, 95, 95, 95, 100.5],
        'low': [85] * 25 + [94, 94, 100.1, 100.1, 100.1],
        'close': [88] * 25 + [94.5, 94.5, 100.2, 100.2, 100.2],
        'volume': [1000] * 30
    }
    df = pd.DataFrame(data)
    df.index = pd.date_range("2023-01-01", periods=30, freq="15min")
    
    # breakout_level will be 95 (max of indices 25-28)
    # Candle hold count will check back from index 29:
    # index 29: close 100.2 > 95 -> hold=1
    # index 28: close 100.2 > 95 -> hold=2
    # index 27: close 100.2 > 95 -> hold=3
    # index 26: close 94.5 < 95 -> BREAK
    
    res = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df)
    
    print(f"Breakout Level: {res.get('breakout_level')}")
    print(f"Candle Hold Count: {res.get('candle_hold_count')}")
    print(f"Price Reclaim (2+ candles): {res.get('price_reclaim')}")
    
    assert res.get('candle_hold_count', 0) == 3
    assert res.get('price_reclaim') == True
    print("SUCCESS: 3-candle hold confirmed with price_reclaim=True.")

if __name__ == "__main__":
    try:
        test_breakout_hold_validation()
        print("\nSUCCESS: V6.3 REFINEMENTS VERIFIED (TA CORE).")
    except Exception as e:
        print(f"\nFAILURE: VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
