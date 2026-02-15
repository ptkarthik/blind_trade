
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

async def verify_expansion():
    from app.services.market_data import market_service
    from app.services.scanner_engine import scanner_engine
    
    print("--- MarketData Expansion Verification ---")
    print(f"Total symbols in master: {len(market_service.stock_master)}")
    
    # Check for some Nifty 500 symbols that weren't in the original static list
    sample_symbols = ["3MINDIA.NS", "SUZLON.NS", "IDEA.NS", "ZEEL.NS"]
    for sym in sample_symbols:
        found = any(s["symbol"] == sym for s in market_service.stock_master)
        print(f"Checking {sym}: {'FOUND' if found else 'NOT FOUND'}")
        
    print("\n--- Advisor Logic (ROI CAGR) Verification ---")
    # Test advisor output with a mock buy signal
    from app.services.advisor_engine import advisor_engine
    
    mock_fund = {"score": 85, "rev_cagr": 0.15, "intrinsic_value": 3000, "valuation_gap": 20, "moat_score": 8}
    mock_ta = {"trend_score": 85, "mom_score": 75, "ema_200_val": 2400, "levels": {"support": [{"price": 2450, "label": "S1", "strength": "Strong"}]}}
    mock_risk = {"beta": 0.8, "stability_score": 80, "max_drawdown": 15}
    mock_sector = {"alpha": 0.05}
    
    advice = advisor_engine.generate_advice("RELIANCE.NS", 2500, mock_fund, mock_ta, mock_risk, mock_sector)
    
    print(f"Play Type: {advice['holding_period']['play_type']}")
    print(f"Projected ROI CAGR: {advice['targets']['projected_cagr']}%")
    print(f"Target Price: {advice['targets']['3_year_target']}")
    print(f"Scenario 1 Probability: {advice['scenarios'][0]['probability']}")

if __name__ == "__main__":
    asyncio.run(verify_expansion())
