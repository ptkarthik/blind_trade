import pandas as pd
import numpy as np
import asyncio
import sys
import os

# Ensure backend path is available
sys.path.append(os.getcwd())

from app.services.ta_intraday import ta_intraday
from datetime import datetime, timedelta

async def verify_elite_setup():
    print("\n--- ELITE LOGIC VERIFICATION ---")
    
    # 1. Create a "Perfect Storm" Dataset
    base_time = datetime(2026, 3, 11, 9, 15)
    prices = [100]*75 # Yesterday (flat)
    
    # Today start
    # 09:15 - 09:45 (First 30 mins) -> Range [100, 105]
    today_start = [100, 102, 105, 103, 101, 104] 
    prices += today_start
    
    # 09:45 - 10:15 -> Dip below 100 (S1/VWAP proxy) and RECLAIM
    prices += [99.5, 99.0, 98.5, 100.5, 102.5, 105.0] # Trap at 98.5, Reclaim at 100.5
    
    # 10:15 - 11:15 -> Breakout above ORB High (105)
    prices += [106, 107, 108, 109, 110, 111, 112]
    
    times = [base_time + timedelta(minutes=5*i) for i in range(len(prices))]
    
    df = pd.DataFrame({
        "open": prices, "high": [p+0.2 for p in prices], "low": [p-0.2 for p in prices], 
        "close": prices, "volume": [1000]*len(prices)
    }, index=times)
    
    # Inject Volume SPIKE at reclaim (index 75 + 6 + 3 = 84)
    df.iloc[84, df.columns.get_loc('volume')] = 5000
    
    # Use ta_intraday to analyze
    ta_res = ta_intraday.analyze_stock(df)
    
    print(f"VWAP: {ta_res.get('vwap_val', 0):.2f}")
    print(f"ORB High: {ta_res['orb'].get('orb_high')}")
    print(f"ORB Status: {ta_res['orb'].get('status')}")
    print(f"Trap Detected: {ta_res['trap'].get('is_trap')}")
    if ta_res['trap'].get('is_trap'):
        print(f"Trap Level: {ta_res['trap'].get('level')}")
    
    # Check if high conviction triggers
    if ta_res['orb'].get('status') == 'Breakout' and ta_res['trap'].get('is_trap'):
        print("\n🏆 ELITE PATTERN VERIFIED: ORB Breakout + Institutional Trap Detected.")
    else:
        print("\n❌ VERIFICATION FAILED: Patterns not detected as expected.")

if __name__ == "__main__":
    asyncio.run(verify_elite_setup())
