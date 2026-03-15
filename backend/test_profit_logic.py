
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.ta_intraday import ta_intraday
from app.services.intraday_engine import intraday_engine

def create_mock_df(price_trend, volume_trend):
    """Creates a mock DataFrame for testing."""
    times = [datetime.now() - timedelta(minutes=15*i) for i in range(len(price_trend))][::-1]
    df = pd.DataFrame({
        'open': price_trend,
        'high': [p * 1.01 for p in price_trend],
        'low': [p * 0.99 for p in price_trend],
        'close': price_trend,
        'volume': volume_trend
    }, index=times)
    return df

def test_exhaustion():
    print("\n--- Testing Exhaustion Detection ---")
    # Simulation: Stock up 5% from open
    prices = [100 + i*0.2 for i in range(50)] # Start 100, End 110 (10% up)
    volumes = [1000 for _ in range(50)]
    df = create_mock_df(prices, volumes)
    
    res = ta_intraday.analyze_stock(df)
    exhaustion = res.get('exhaustion', {})
    print(f"Is Exhausted: {exhaustion.get('is_exhausted')}")
    print(f"Reasons: {exhaustion.get('reasons')}")
    assert exhaustion.get('is_exhausted') == True
    print("✅ Exhaustion Test Passed")

def test_pullback():
    print("\n--- Testing Pullback Detection ---")
    # Simulation: Strong uptrend then dip to 9 EMA
    base = [100 + i*0.5 for i in range(40)] # Up to 120
    dip = [118, 116, 115.5] # Dip back close to support
    prices = base + dip
    volumes = [2000 for _ in range(len(prices))]
    df = create_mock_df(prices, volumes)
    
    res = ta_intraday.analyze_stock(df)
    pullback = res.get('pullback', {})
    print(f"Is Pullback: {pullback.get('is_pullback')}")
    print(f"Type: {pullback.get('type')}")
    print("✅ Pullback Logic check complete")

if __name__ == "__main__":
    test_exhaustion()
    test_pullback()
