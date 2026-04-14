import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

sys.path.append(os.getcwd())
from app.services.intraday_engine import intraday_engine

def create_mock_df(price_trend, volume_trend):
    # Create 20 candles of data
    data = {
        'open': [100 + i*price_trend for i in range(20)],
        'high': [102 + i*price_trend for i in range(20)],
        'low': [98 + i*price_trend for i in range(20)],
        'close': [100 + i*price_trend for i in range(20)],
        'volume': [1000 * volume_trend for i in range(20)]
    }
    df = pd.DataFrame(data)
    df.attrs['symbol'] = "MOCK_STOCK"
    return df

def test_pioneer_logic():
    print("--- [MOCK PIONEER LOGIC TEST] ---")
    
    # 1. TEST Market Regime Penalty (Strong Bearish)
    print("\nScenario 1: Nifty Strong Bearish")
    mock_df = create_mock_df(0.5, 1.5) # Trending up, but market is weak
    mock_1h = create_mock_df(0.5, 1.5)
    
    indicators = intraday_engine._get_indicators(mock_df, mock_1h)
    market_ctx = {"market_regime": "Strong Bearish", "is_sideways": False}
    l2_data = {"mode": "MOMENTUM"}
    liq = {"adv20": 1000000, "level": "High"}
    
    penalty, res = intraday_engine._run_layer3(indicators, mock_df, market_ctx, l2_data, liq)
    print(f"Market Weakness Penalty? {'Yes' if any('Market Weakness' in r['text'] for r in res['reasons']) else 'No'}")
    for r in res['reasons']: print(f"  Reason: {r['text']} (Impact: {r['impact']})")

    # 2. TEST Strict Structure (Broken trend)
    print("\nScenario 2: Broken Structure (Price sliced below recent low)")
    # Force last candle below min of last 5
    broken_df = create_mock_df(0.1, 1.0)
    # Set current price low
    broken_df.iloc[-1, broken_df.columns.get_loc('close')] = 95 
    
    inds_broken = intraday_engine._compute_indicators(broken_df)
    print(f"Structure OK? {inds_broken['structure_ok']}")

    # 3. TEST Dynamic Exhaustion (ATR-based)
    print("\nScenario 3: Dynamic Exhaustion (3x ATR)")
    # Create very extended price
    ext_df = create_mock_df(0, 1.0)
    # Close far from EMA20
    inds_ext = intraday_engine._compute_indicators(ext_df)
    # Price is 100, EMA20 is 100 in mock script (static). Let's force a gap.
    # In _compute_indicators, EMA20 is calculated from the df.
    print(f"Price: {inds_ext['price']}, EMA20: {inds_ext['ema20']}, Distance EMA: {inds_ext['distance_ema']}")
    print(f"Exhausted? {inds_ext['is_exhausted']}")

if __name__ == "__main__":
    test_pioneer_logic()
