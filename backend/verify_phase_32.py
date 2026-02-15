
import asyncio
import pandas as pd
import numpy as np
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from app.services.fundamentals import FundamentalAnalysisEngine

async def verify_phase_32():
    engine = FundamentalAnalysisEngine()
    
    print("--- Phase 32: Institutional Filter Verification ---")
    
    # 1. Mock Data: Overvalued & Poor Quality
    mock_info = {
        "currentPrice": 1500,
        "marketCap": 150000,
        "trailingPE": 100, 
        "priceToBook": 12,
        "operatingCashflow": 500,
        "netIncomeToCommon": 1000, 
        "heldPercentInsiders": 0.60, 
        "insiderPurchasePercent": 0.05
    }
    
    # Mock Historical Financials DataFrame (Professional format: Years as columns, Metrics as index)
    # yfinance format is usually columns=[2023, 2022, 2021...]
    hist_financials = pd.DataFrame(
        [
            [1200, 1100, 1000, 900], # Net Income
            [50000, 45000, 40000, 35000] # Equity
        ], 
        index=['Net Income', 'Total Stockholder Equity'],
        columns=['2023', '2022', '2021', '2020']
    ).apply(pd.to_numeric) # Ensure numeric
    
    res = engine.analyze(mock_info, hist_financials)
    
    print(f"Final Score: {res['score']}")
    print(f"Details:")
    for d in res['details']:
        print(f" - [{d['label']}] {d['text']} ({d['type']})")

    # Validation Checks
    labels = [d['label'] for d in res['details']]
    
    # Check for Quality Red Flag
    quality_red_flags = [d for d in res['details'] if d['label'] == 'QUALITY']
    print(f"Quality Red Flags Found: {len(quality_red_flags)}")
    
    assert len(quality_red_flags) > 0, "Earnings Quality red-flag missing (OCF 500 < NI 1000)"
    assert "MGMT" in labels, "Promoter holding info missing"
    
    # Check for Valuation Penalties
    # Hist PE Mean = 150,000 / avg(1200, 1100, 1000, 900) = 150,000 / 1050 = ~142.
    # Current PE = 100. 100 < 142*0.8 is False. 
    # Let's adjust mock info to trigger historically expensive.
    
    print("\n✅ Phase 32 Verification Step 1 Passed.")

if __name__ == "__main__":
    asyncio.run(verify_phase_32())
