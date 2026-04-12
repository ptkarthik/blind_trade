import pandas as pd
import numpy as np
import sys
import os

# Mock the indicators
indicators = {
    "price": 105.0,
    "ema20": 100.0,
    "ema_slope": 0.5,
    "vwap": 104.5,
    "distance_vwap": 0.48, # Near VWAP (< 1.5)
    "distance_ema": 5.0,
    "rvol": 2.5,
    "structure_ok": True,
    "is_pullback": False,
    "is_exhausted": False,
    "ema_1h_trend_up": True,
    "atr": 2.0
}

def _run_layer1(indicators):
    price, ema20, ema_slope = indicators["price"], indicators["ema20"], indicators["ema_slope"]
    distance_vwap, rvol = indicators["distance_vwap"], indicators["rvol"]
    score, reasons = 0, []
    
    if price > ema20: score += 10; reasons.append("Price above EMA20")
    if ema_slope > 0: score += 10; reasons.append("EMA20 trending up")
    if abs(distance_vwap) < 1.5: score += 10; reasons.append("Near VWAP")
    if rvol > 2: score += 10; reasons.append("High RVOL")
    
    return min(40, score), {"score": score, "reasons": reasons}

def _run_layer2(indicators):
    is_exhausted = indicators.get("is_exhausted", False)
    if is_exhausted: return 0, {"mode": "EXHAUSTED"}
    
    score = 0
    # EARLY mode
    score += 45
    # High RVOL booster
    score += 10
    # 1H Trend booster
    score += 5
    
    return min(60, score), {"score": score, "mode": "EARLY"}

l1, l1_data = _run_layer1(indicators)
l2, l2_data = _run_layer2(indicators)

print(f"L1 Score: {l1} / 40")
print(f"L2 Score: {l2} / 60")
print(f"Total Score: {l1 + l2} / 100")

# Test Exhaustion
indicators["is_exhausted"] = True
l2_ext, _ = _run_layer2(indicators)
print(f"L2 Score (Exhausted): {l2_ext}")
