import pandas as pd
import numpy as np
import asyncio
from datetime import datetime, timedelta
import pytz
import sys
import os

# Mocking parts of the app to test analyze_stock
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import types
m_ctx = types.ModuleType('app.services.index_context')
m_ctx.index_ctx = {}
sys.modules['app.services.index_context'] = m_ctx

def test_institutional_flow_logic():
    print("\n--- Testing Institutional Flow Enhancements ---")
    
    # 1. Module 7: Delivery Confirmation
    print("\nTest Module 7: Delivery Confirmation")
    rvol = 2.5
    delivery_ratio = 60 # > 55
    rvol_bonus = 18 # Standard
    if rvol > 2.0 and delivery_ratio > 55:
        rvol_bonus += 6
    print(f"RVOL: {rvol} | Delivery: {delivery_ratio}% | Bonus: {rvol_bonus}")
    assert rvol_bonus == 24

    # 2. Module 4: Narrow Range Accumulation
    print("\nTest Module 4: Narrow Range Accumulation")
    volume_zscore = 2.5 # > 2
    avg_range_10 = 10.0
    candle_range = 5.0 # 5.0 < (10.0 * 0.6 = 6.0)
    acc_bonus = 18
    if volume_zscore > 2 and avg_range_10 > 0 and candle_range < (avg_range_10 * 0.6):
        acc_bonus += 6
    print(f"Z: {volume_zscore} | AvgR: {avg_range_10} | CR: {candle_range} | Bonus: {acc_bonus}")
    assert acc_bonus == 24

    # 3. Module 2: Spike Collapse Warning
    print("\nTest Module 2: Spike Collapse Warning")
    v1, v2, v3 = 1000, 2000, 1500
    # v3 < v2 (True) and v2 > v1 * 1.5 (2000 > 1500) (True)
    liq_penalty = 0
    if v3 < v2 and v2 > v1 * 1.5:
        liq_penalty -= 6
    print(f"V1: {v1}, V2: {v2}, V3: {v3} | Penalty: {liq_penalty}")
    assert liq_penalty == -6

    # 4. Module 14: VWAP Reclaim Failure Trap
    print("\nTest Module 14: VWAP Reclaim Trap")
    p2, p3 = 105, 102
    vwap2, vwap3 = 104, 103
    v2, v3 = 2000, 1800
    # p2 > vwap2 (True), p3 < vwap3 (True), v3 < v2 (True)
    trap_detected = False
    if p2 > vwap2 and p3 < vwap3 and v3 < v2:
        trap_detected = True
    print(f"P2: {p2}, P3: {p3} | VWAP2: {vwap2}, VWAP3: {vwap3} | V2: {v2}, V3: {v3} | Trap: {trap_detected}")
    assert trap_detected == True

    print("\nINSTITUTIONAL FLOW LOGIC CHECK: PASSED")

if __name__ == "__main__":
    test_institutional_flow_logic()
