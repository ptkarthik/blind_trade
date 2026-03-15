
import pandas as pd
import numpy as np
from app.services.ta_intraday import ta_intraday
from app.services.intraday_engine import intraday_engine
import asyncio

from unittest.mock import patch, MagicMock

async def simulate_scenarios():
    print("🚀 Simulating Tactical Strategy Logic...")
    
    # 5m candles (approx 75 candles for 1 day)
    dates = pd.date_range("2026-03-02 09:15", periods=75, freq="5min")
    base_df = pd.DataFrame({
        "open": [100.0] * 75,
        "high": [100.5] * 75,
        "low": [99.5] * 75,
        "close": [100.0] * 75,
        "volume": [1000] * 75
    }, index=dates)

    # SCENARIO 1: EXHAUSTED (Late Entry)
    exh_df = base_df.copy()
    # Mock a straight run up from 100 to 105 (+5%)
    # This should trigger the EXHAUSTION penalty (-35)
    exh_df['close'] = np.linspace(100, 105, 75)
    exh_df['high'] = exh_df['close'] + 0.1
    
    # SCENARIO 2: PULLBACK (Early Setup)
    pb_df = base_df.copy()
    # Mock a run to 104, then a dip back to 101.5 (near VWAP)
    # This should trigger the PULLBACK bonus (+25)
    close_vals = list(np.linspace(100, 104, 40)) + list(np.linspace(104, 101.5, 35))
    pb_df['close'] = close_vals
    pb_df['high'] = pb_df['close'] + 0.1
    pb_df['low'] = pb_df['close'] - 0.1

    from app.services.market_data import market_service
    
    # Patch the INSTANCE methods
    async def mock_ohlc_fn(*a, **k):
        return exh_df if "OVERRUN" in a[0] else pb_df
    
    async def mock_live_fn(*a, **k):
        return 105.0 if "OVERRUN" in a[0] else 101.5

    with patch.object(market_service, 'get_ohlc', side_effect=mock_ohlc_fn):
        with patch.object(market_service, 'get_latest_price', side_effect=mock_live_fn):
            
            print("\n--- [⚠️ SCENARIO 1: EXHAUSTED / LATE ENTRY] ---")
            res_exh = await intraday_engine.analyze_stock("OVERRUN.NS", fast_fail=True)
            if res_exh:
                print(f"Logic Type: {res_exh.get('logic_type')}")
                print(f"Final Score: {res_exh.get('score')}")
                print(f"Verdict: {res_exh.get('verdict')}")
            else:
                print("Failed to analyze Scenario 1")

            print("\n--- [🛡️ SCENARIO 2: PULLBACK / PRO SETUP] ---")
            res_pb = await intraday_engine.analyze_stock("SETUP.NS", fast_fail=True)
            if res_pb:
                print(f"Logic Type: {res_pb.get('logic_type')}")
                print(f"Final Score: {res_pb.get('score')}")
                print(f"Verdict: {res_pb.get('verdict')}")
            else:
                print("Failed to analyze Scenario 2")

if __name__ == "__main__":
    # We need to monkeypatch analyze_stock to accept mock_df or just use it.
    # Looking at intraday_engine, it calls market_service.get_ohlc.
    # I'll manually inject it if possible or just rely on the logic I know is there.
    # Wait, intraday_engine.analyze_stock doesn't take mock_df. 
    # Let me just run a simplified version of the logic for the simulation.
    asyncio.run(simulate_scenarios())
