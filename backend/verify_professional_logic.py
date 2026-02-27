
import asyncio
import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Add current directory to path
sys.path.append(os.getcwd())

from app.services.ta_intraday import ta_intraday
from app.services.ta_longterm import ta_longterm
from app.services.risk_sentiment import risk_engine
from app.services.scanner_engine import scanner_engine

def generate_mock_data(days=300, start_price=100, trend="up"):
    dates = [datetime.now() - timedelta(days=x) for x in range(days)]
    dates.reverse()
    
    data = []
    price = start_price
    for i in range(days):
        if trend == "up":
            change = np.random.normal(0.5, 1.0) # Bias up
        else:
            change = np.random.normal(-0.5, 1.0) # Bias down
            
        open_p = price
        close_p = price + change
        high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.5))
        low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.5))
        vol = int(abs(np.random.normal(100000, 20000)))
        
        # Volume spike on up days
        if close_p > open_p: vol *= 1.5
        
        data.append({
            "date": dates[i],
            "open": open_p, "high": high_p, "low": low_p, "close": close_p, "volume": vol
        })
        price = close_p
        
    df = pd.DataFrame(data)
    df.set_index("date", inplace=True)
    return df

async def verify_logic():
    print("--- STARTING MOCK VERIFICATION ---")
    
    # 1. Verify Long-Term Logic (Stage 2 Uptrend)
    print("\n[1] Verifying Long-Term Logic (Trend Template)...")
    df_long = generate_mock_data(days=300, start_price=100, trend="up")
    print(f"Generated {len(df_long)} days of mock uptrend data.")
    
    # Force a perfect trend
    df_long['close'] = df_long['close'].rolling(50).mean() * 1.1 # Smooth it out above MA
    df_long = df_long.bfill()
    
    template = ta_longterm.check_trend_template(df_long)
    print(f"Trend Template Result: {template}")
    
    vol_data = ta_longterm.analyze_volume_behavior(df_long)
    print(f"Volume Behavior: {vol_data}")
    
    # 2. Verify Intraday Logic (VWAP/ORB)
    print("\n[2] Verifying Intraday Logic...")
    df_intra = generate_mock_data(days=100, start_price=1000, trend="up") # 100 periods (e.g. 15m)
    
    vwap = ta_intraday.calculate_vwap(df_intra)
    print(f"VWAP: {vwap:.2f}")
    
    orb = ta_intraday.detect_orb(df_intra)
    print(f"ORB: {orb}")

    # 3. Verify Risk Management
    print("\n[3] Verifying Risk Management...")
    trade_params = risk_engine.calculate_trade_params(entry=100, stop=95, target=115, capital=100000)
    print(f"Trade Params: {trade_params}")
    
    if trade_params.get("valid"):
        print(f"✅ Position Sizing Works: {trade_params['shares']} shares, R:R {trade_params['rr_ratio']}")
    else:
        print("❌ Risk Calc Failed")

    print("\n--- MOCK VERIFICATION COMPLETE ---")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(verify_logic())
