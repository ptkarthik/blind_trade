
import asyncio
import sys
import os

sys.path.append(os.getcwd())

from app.services.advisor_engine import advisor_engine

def test_mock_tactical():
    print("--- MOCK VERIFICATION: Tactical Momentum & Smart Entry ---")
    
    # Simulate an explosive momentum/breakout stock
    current_price = 100.0
    fund_res = {
        "score": 55.0,
        "raw_metrics": {"rev_cagr": 0.12, "roe": 0.14, "valuation_gap": 10.0, "beta": 1.2}
    }
    ta_res = {
        "trend_score": 90,
        "mom_score": 85,
        "squeeze": {"firing": True}, # Breakout!
        "ema_200_val": 80.0
    }
    risk_res = {"max_drawdown": 15, "recovery_speed": "Fast"}
    sector_res = {"alpha": 0.05}
    
    advisory = advisor_engine.generate_advice(
        "MOCK", current_price, fund_res, ta_res, risk_res, sector_res
    )
    
    ea = advisory.get("entry_analysis", {})
    hp = advisory.get("holding_period", {})
    
    print(f"Price: {current_price}")
    print(f"Entry Price: {ea.get('entry_price')}")
    print(f"Entry Type: {ea.get('entry_type')}")
    print(f"Rationale: {ea.get('rationale')}")
    
    if ea.get('entry_type') == "Buy Stop (Breakout)" and ea.get('entry_price') == current_price:
        print("\n✅ SUCCESS: Correct Breakout Entry Logic (No premium, Buy Stop label).")
    else:
        print("\n❌ FAILED: Unexpected Entry Logic.")

if __name__ == "__main__":
    test_mock_tactical()
