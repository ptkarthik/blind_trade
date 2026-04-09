import asyncio
import sys
from unittest.mock import MagicMock, patch
import pandas as pd

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.services.intraday_engine import IntradayEngine

async def test():
    engine = IntradayEngine()
    # Ensure flags are ON
    engine.SCORING_FLAGS["enable_dynamic_alpha"] = True
    engine.SCORING_FLAGS["debug_alpha_mode"] = True
    engine.SCORING_FLAGS["enable_dynamic_dna"] = True
    
    # Mock data showing 0.5% breakout from VWAP (100 -> 100.5)
    dates = pd.date_range("2026-04-09 09:15", periods=30, freq="15min")
    df = pd.DataFrame({
        "open": [100.2]*30, 
        "close": [100.5]*30, 
        "high": [100.8]*30, 
        "low": [100.1]*30, 
        "volume": [5000.0]*30
    }, index=dates)
    
    # Mock TA values: PASS DNA (>20) and Recalibrated Vol (>1.0)
    ta_mock = {
        "vwap_val": 100.0, 
        "rvol_val": 1.1, # This used to fail (required 1.2/1.5)
        "vwap_score": 100, 
        "adx_score": 100, 
        "pa_score": 100, 
        "ema20": 100.0, 
        "ema20_prev": 99.5
    }
    
    with patch("app.services.market_data.market_service.get_ohlc", return_value=df):
        # We MUST patch where it is IMPORTED in intraday_engine
        with patch("app.services.intraday_engine.ta_intraday.analyze_stock", return_value=ta_mock):
            with patch("app.services.intraday_engine.ta_intraday.detect_pullback_entry_v45", return_value={"is_entry": False}):
                with patch("app.services.intraday_engine.ta_intraday.detect_micro_trend", return_value={"hh_hl": True}):
                    res = await engine.analyze_stock("TEST", pulse_data={"TEST": df})
                    
                    if "groups" not in res:
                        print(f"ERROR: {res.get('skip_reason')}")
                        return

                    # EXTRA DIAGNOSTICS
                    print("\n--- ENGINE LOGIC AUDIT ---")
                    # We can't see the local variables directly but we can see the results
                    print(f"DNA Score: {res['groups']['DNA (40%)']['score']}")
                    print(f"RVOL: {ta_mock['rvol_val']}")
                    real_price_mock = df['close'].iloc[-1]
                    print(f"Distance from VWAP: {abs(real_price_mock-ta_mock['vwap_val'])/ta_mock['vwap_val']}")
                    
                    print(f"\nRESULT_L2_SCORE: {res['groups']['Alpha Edge (60%)']['score']}")
                    print(f"RESULT_ALPHA_MODE: {res.get('alpha_mode')}")
                    print("REASONS:")
                    for r in res.get('reasons', []):
                        if r['layer'] == 2:
                             print(f"   [L2] {r['text']}: +{r['impact']}")
                        elif r['layer'] == 1:
                             print(f"   [L1] {r['text']}: +{r['impact']}")

if __name__ == "__main__":
    asyncio.run(test())
