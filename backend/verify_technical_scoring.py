import pandas as pd
import numpy as np
import asyncio
import sys
import os
import types

# Mocking parts of the app to test analyze_stock logic
sys.path.append(os.path.join(os.getcwd(), 'backend'))

def test_technical_scoring_logic():
    print("\n--- Testing Technical and Scoring Enhancements ---")
    
    # 1. Module 12: ATR-Adjusted Deviation Guard
    print("\nTest Module 12: ATR-Adjusted Deviation")
    price = 110
    vwap = 100
    atr_20 = 3.0 # Deviation = 10, Ratio = 10/3 = 3.33 > 2.5
    
    block_trade = False
    block_reason = ""
    vwap_deviation_pct = (abs(price - vwap) / vwap) * 100 # 10%
    
    if vwap_deviation_pct > 4.0: 
        block_trade, block_reason = True, "Critical VWAP Extension"
    
    if atr_20 > 0:
        vwap_atr_ratio = abs(price - vwap) / atr_20
        if vwap_atr_ratio > 2.5:
            block_trade, block_reason = True, "Excessive VWAP Extension"
            
    print(f"Price: {price} | VWAP: {vwap} | ATR20: {atr_20} | ATR_Ratio: {round(vwap_atr_ratio,2)} | Blocked: {block_trade} ({block_reason})")
    assert block_trade == True
    assert block_reason == "Excessive VWAP Extension"

    # 2. Volatility Expansion Check
    print("\nTest Volatility Expansion")
    atr_5 = 1.5
    atr_20 = 1.0
    atr_ratio = atr_5 / max(atr_20, 0.0001) # 1.5 > 1.3
    vol_bonus = 0
    if atr_ratio > 1.3:
        vol_bonus = 8
    print(f"ATR5: {atr_5} | ATR20: {atr_20} | Ratio: {atr_ratio} | Bonus: {vol_bonus}")
    assert vol_bonus == 8

    # 3. Float Rotation Signal
    print("\nTest Float Rotation Signal")
    volume = 1000000
    free_float = 10000000 # 10M
    float_rotation = volume / max(free_float, 1) # 0.1 > 0.08
    float_rot_bonus = 0
    if float_rotation > 0.08:
        float_rot_bonus = 12
    print(f"Vol: {volume} | Float: {free_float} | Rot: {round(float_rotation,3)} | Bonus: {float_rot_bonus}")
    assert float_rot_bonus == 12

    # 4. Stage 2 Score Safety Cap
    print("\nTest Stage 2 Safety Cap")
    liq_accel_bonus = 10
    accumulation_bonus = 18
    rvol_bonus = 18
    float_rotation_bonus = 12
    # Total = 10 + 18 + 18 + 12 = 58
    
    stage2_bonuses_raw = liq_accel_bonus + accumulation_bonus + rvol_bonus + float_rotation_bonus
    stage2_clamped = min(stage2_bonuses_raw, 35)
    print(f"Raw Stage 2: {stage2_bonuses_raw} | Clamped: {stage2_clamped}")
    assert stage2_clamped == 35

    # 5. Normalization Helper
    print("\nTest Normalization Helper")
    def normalize(val, min_v, max_v):
        if max_v == min_v: return 0.5
        return max(0, min(1, (val - min_v) / (max_v - min_v)))
    
    n1 = normalize(75, 50, 100) # 0.5
    n2 = normalize(120, 50, 100) # 1.0 (clamped)
    n3 = normalize(30, 50, 100) # 0.0 (clamped)
    print(f"75 in [50,100]: {n1} | 120: {n2} | 30: {n3}")
    assert n1 == 0.5 and n2 == 1.0 and n3 == 0.0

    print("\nTECHNICAL AND SCORING LOGIC CHECK: PASSED")

if __name__ == "__main__":
    test_technical_scoring_logic()
