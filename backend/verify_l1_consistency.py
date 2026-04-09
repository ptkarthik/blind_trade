import asyncio
import sys
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.services.intraday_engine import IntradayEngine

async def test_l1_consistency():
    engine = IntradayEngine()
    
    # CASE 1: Low Scores (Should be 0.0 pts and 'negative')
    ta_low = {
        "vwap_val": 100.0, 
        "rvol_val": 1.2,
        "vwap_score": 30, # Below 40 floor
        "adx_score": 20, # Below 25 floor
        "pa_score": 30,  # Below 40 floor
        "ema20": 100.0, 
        "ema20_prev": 99.5,
        "bias": "Bullish"
    }
    
    # CASE 2: High Scores (Should be Max pts and 'positive')
    ta_high = {
        "vwap_val": 100.0, 
        "rvol_val": 2.0,
        "vwap_score": 100,
        "adx_score": 100,
        "pa_score": 100,
        "ema20": 100.0, 
        "ema20_prev": 99.5,
        "bias": "Bullish"
    }

    dates = pd.date_range("2026-04-09 09:15", periods=30, freq="15min")
    df = pd.DataFrame({
        "open": [100.2]*30, "close": [100.5]*30, "high": [100.8]*30, "low": [100.1]*30, "volume": [5000.0]*30
    }, index=dates)

    print("--- TESTING L1 CONSISTENCY ---")

    for name, ta_mock in [("LOW_SCORE", ta_low), ("HIGH_SCORE", ta_high)]:
        print(f"\nScenario: {name}")
        with patch("app.services.market_data.market_service.get_ohlc", return_value=df):
            with patch("app.services.intraday_engine.ta_intraday.analyze_stock", return_value=ta_mock):
                with patch("app.services.intraday_engine.ta_intraday.detect_pullback_entry_v45", return_value={"is_entry": False}):
                    with patch("app.services.intraday_engine.ta_intraday.detect_micro_trend", return_value={"hh_hl": True}):
                        res = await engine.analyze_stock("TEST", pulse_data={"TEST": df})
                        
                        for r in res.get('reasons', []):
                            if r['layer'] == 1:
                                print(f"   [L1] {r['text']}: {r['impact']} pts | Type: {r['type']}")

if __name__ == "__main__":
    asyncio.run(test_l1_consistency())
