
import pandas as pd
import numpy as np
from datetime import datetime

def test_v33_sweep_logic():
    print("Starting Stand-alone V3.3 Sweep Logic Verification...")
    
    def get_sweep_status(df, breakout_level):
        latest = df.iloc[-1]
        
        # 1. BREAKOUT DETECTION (In last 3 candles)
        had_breakout = False
        breakout_index = -1
        for i in range(-3, 0):
            if df.iloc[i]['high'] > breakout_level and df.iloc[i]['close'] > breakout_level:
                had_breakout = True
                breakout_index = i
                break

        # 2. LIQUIDITY SWEEP DETECTION
        liquidity_sweep = False
        
        # Condition A: Wick High > Level AND Close < Level
        cond_a = latest['high'] > breakout_level and latest['close'] < breakout_level
        
        # Condition B: Closes back below within 2 candles
        cond_b = False
        if had_breakout:
            if breakout_index == -3 and latest['close'] < breakout_level:
                cond_b = True
            if breakout_index == -2 and latest['close'] < breakout_level:
                cond_b = True
        
        # Condition C: Volume spike but fail to hold
        vol_ma = df['volume'].rolling(20).mean().iloc[-1]
        rvol = latest['volume'] / vol_ma if vol_ma > 0 else 1.0
        cond_c = rvol > 1.8 and latest['high'] > breakout_level and latest['close'] < breakout_level
        
        if cond_a or cond_b or cond_c:
            liquidity_sweep = True

        # 3. SAFE RE-ENTRY CHECK
        price_reclaim = False
        if len(df) >= 3:
            last_3 = df.tail(3)
            if (last_3['close'] > breakout_level).all():
                price_reclaim = True

        return liquidity_sweep, price_reclaim, rvol

    # Scenarios
    breakout_lvl = 100.0
    
    # Base Data (20 periods of chop below 100)
    base_data = {
        "high": [98.0] * 20,
        "low": [96.0] * 20,
        "open": [97.0] * 20,
        "close": [97.5] * 20,
        "volume": [1000] * 20
    }
    
    # Scenario 1: Immediate Wick Rejection (Condition A)
    s1_data = {
        "high": base_data["high"] + [102.0],
        "low": base_data["low"] + [99.0],
        "open": base_data["open"] + [99.5],
        "close": base_data["close"] + [98.5],
        "volume": base_data["volume"] + [2500] # High RVOL
    }
    df1 = pd.DataFrame(s1_data)
    sweep1, reclaim1, rvol1 = get_sweep_status(df1, breakout_lvl)
    print(f"Scenario 1 (Wick Trap): Sweep={sweep1}, Reclaim={reclaim1}, RVOL={rvol1:.2f} -> {'PASS' if sweep1 and not reclaim1 else 'FAIL'}")

    # Scenario 2: Breakout then Rejection (Condition B)
    # Candle -3: Breakout
    # Candle -2: Hold
    # Candle -1: Rejection below
    s2_data = {
        "high": base_data["high"] + [101.5, 101.5, 99.5],
        "low": base_data["low"] + [100.5, 100.2, 98.0],
        "open": base_data["open"] + [100.6, 101.0, 101.0],
        "close": base_data["close"] + [101.0, 101.2, 98.5],
        "volume": base_data["volume"] + [1500, 1200, 2000]
    }
    df2 = pd.DataFrame(s2_data)
    sweep2, reclaim2, rvol2 = get_sweep_status(df2, breakout_lvl)
    print(f"Scenario 2 (Fast Rejection): Sweep={sweep2}, Reclaim={reclaim2} -> {'PASS' if sweep2 and not reclaim2 else 'FAIL'}")

    # Scenario 3: Safe Reclaim
    # Candle -3: Above
    # Candle -2: Above
    # Candle -1: Above
    s3_data = {
        "high": base_data["high"] + [102.0, 102.5, 103.0],
        "low": base_data["low"] + [100.5, 101.0, 101.5],
        "open": base_data["open"] + [100.6, 101.5, 102.0],
        "close": base_data["close"] + [101.5, 102.0, 102.5],
        "volume": base_data["volume"] + [1500, 1600, 1700]
    }
    df3 = pd.DataFrame(s3_data)
    sweep3, reclaim3, rvol3 = get_sweep_status(df3, breakout_lvl)
    print(f"Scenario 3 (Safe Reclaim): Sweep={sweep3}, Reclaim={reclaim3} -> {'PASS' if not sweep3 and reclaim3 else 'FAIL'}")

if __name__ == "__main__":
    test_v33_sweep_logic()
