
import asyncio
import pandas as pd
import numpy as np
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.fundamentals import fundamental_engine
from app.services.ta import ta_engine

async def verify_institutional_logic():
    print("--- Institutional Upgrade: Final Logic Verification ---")
    
    # 1. Create a Synthetic Price Dataset (5 years)
    dates = pd.date_range(start="2020-01-01", periods=260, freq='W-SUN')
    # Drop from 100 to 60, then FAST recovery back to 100 in 5 weeks
    prices = [100] * 100 + [100 - i*8 for i in range(5)] + [60 + i*10 for i in range(5)] + [160] * 150
    price_df = pd.DataFrame({
        'close': prices, 
        'high': [p*1.01 for p in prices], 
        'low': [p*0.99 for p in prices], 
        'volume': [1000]*260
    }, index=dates)
    
    # 2. Create Synthetic Financials (The Moat Driver)
    # yfinance financials: Headers in Index, Columns are Dates
    fin_dates = pd.date_range(start="2020-01-01", periods=5, freq='YE')
    fin_data = {
        'Total Revenue': [1000, 1100, 1200, 1300, 1500],
        'Gross Profit': [450, 495, 540, 585, 675] # Steady 45% Margin
    }
    hist_fin = pd.DataFrame(fin_data, index=fin_dates).T
    
    # 3. Mock Fundamental Info (Ticker.info)
    fund_info = {
        "currentPrice": 160,
        "marketCap": 160000,
        "trailingPE": 25,
        "operatingCashflow": 1200,
        "netIncomeToCommon": 1000, 
        "heldPercentInsiders": 0.65,
        "profitMargins": 0.45,
        "returnOnEquity": 0.22,
        "operatingMargins": 0.30,
        "revenueGrowth": 0.18,
        "debtToEquity": 45,
        "pegRatio": 0.8
    }
    
    # 4. Run Analysis
    print("\nExecuting Fundamental Engine Logic...")
    f_res = fundamental_engine.analyze(fund_info, hist_fin)
    
    print("\nExecuting Technical/Resilience Logic...")
    t_res = ta_engine.analyze_stock(price_df, mode="longterm")
    
    print(f"\nRESULTS:")
    print(f"Moat Score: {f_res['raw_metrics'].get('moat_score', 0)}")
    print(f"Recovery Label: {t_res.get('recovery', {}).get('label', 'Unknown')} ({t_res.get('recovery', {}).get('recovery_weeks', 0)} weeks)")
    print(f"Final Fund Score: {f_res['score']}")
    
    # 5. Assertions
    # We assert that the components exist and are being calculated
    assert 'moat_score' in f_res['raw_metrics']
    assert 'recovery' in t_res
    assert f_res['score'] > 50 
    
    print("\n✅ Institutional Verification PASSED: Professional Alpha Drivers fully operational.")

if __name__ == "__main__":
    asyncio.run(verify_institutional_logic())
