import asyncio
import sys
from unittest.mock import MagicMock, patch
import pandas as pd

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import IntradayEngine

async def verify_l2_internal():
    engine = IntradayEngine()
    engine.SCORING_FLAGS["enable_dynamic_alpha"] = True
    engine.SCORING_FLAGS["debug_alpha_mode"] = True

    # 1. MOCK DATA
    df_mock = pd.DataFrame({"close": [100.0]*30, "high": [101.0]*30, "low": [99.0]*30, "volume": [1000.0]*30})
    
    # helper to run audit
    async def run_audit(name, ta_mock_data, pb_mock_data, micro_mock_data, price=115.0):
        print(f"\nAudit: {name}")
        # Create a specific DF for this price
        df_local = df_mock.copy()
        df_local.iloc[-1, df_local.columns.get_loc('close')] = price
        
        with patch("app.services.market_data.market_service.get_ohlc", return_value=df_local):
            with patch("app.services.ta_intraday.ta_intraday.analyze_stock", return_value=ta_mock_data):
                with patch("app.services.ta_intraday.ta_intraday.detect_pullback_entry_v45", return_value=pb_mock_data):
                    with patch("app.services.ta_intraday.ta_intraday.detect_micro_trend", return_value=micro_mock_data):
                        res = await engine.analyze_stock("TEST", pulse_data={"TEST": df_local})
                        
                        if "groups" not in res:
                            print(f"   ⚠️ SKIP: {res.get('skip_reason')}")
                            return

                        l2_score = res["groups"]["Alpha Edge (60%)"]["score"]
                        alpha_mode = res.get("alpha_mode")
                        print(f"   Mode: {alpha_mode} | L2 Score: {l2_score}")
                        for r in res["groups"]["Alpha Edge (60%)"]["details"]:
                            print(f"      - {r['text']}: +{r['impact']}")

    # CASE A: MOMENTUM (Price far from VWAP, RVOL high)
    await run_audit(
        "MOMENTUM MODE",
        {"vwap_val": 100.0, "rvol_val": 3.0, "vwap_score": 100, "adx_score": 80, "pa_score": 80, "ema20": 100.0, "ema20_prev": 99.5},
        {"is_entry": False},
        {"hh_hl": True},
        price=115.0 # 15% from vwap
    )

    # CASE B: EARLY (Price near VWAP, RVOL ok)
    await run_audit(
        "EARLY MODE",
        {"vwap_val": 100.0, "rvol_val": 2.1, "vwap_score": 100, "adx_score": 80, "pa_score": 80, "ema20": 100.0, "ema20_prev": 99.5},
        {"is_entry": False},
        {"hh_hl": True},
        price=100.5 # 0.5% from vwap
    )

    # CASE C: DNA SAFETY GATE (L1 < 20)
    await run_audit(
        "DNA BLOCKED",
        {"vwap_val": 100.0, "rvol_val": 3.0, "vwap_score": 0, "adx_score": 0, "pa_score": 0, "ema20": 100.0, "ema20_prev": 99.5},
        {"is_entry": False},
        {"hh_hl": True},
        price=115.0
    )

if __name__ == "__main__":
    asyncio.run(verify_l2_internal())
