import sys
import pandas as pd
import numpy as np

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.services.intraday_engine import intraday_engine

def verify_math():
    print("--- 🧪 INTRADAY ENGINE MATH VERIFICATION ---")
    
    # 1. Setup a clean, strongly trending dataframe
    dates = pd.date_range("2026-04-10 09:15", periods=50, freq="15min")
    df = pd.DataFrame(index=dates)
    df['open'] = np.linspace(100, 110, 50)
    df['high'] = df['open'] + 1
    df['low'] = df['open'] - 0.5
    df['close'] = df['open'] + 0.8
    # Add a massive volume spike at the end to trigger RVOL > 2.0
    vols = [1000] * 48 + [5000, 6000] 
    df['volume'] = vols
    
    df_1h = df.resample('1h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
    
    # 2. Extract Indicators
    indicators = intraday_engine._get_indicators(df, df_1h)
    
    print("\n--- 1. INDICATORS ---")
    print(f"Price: {indicators['price']:.2f}")
    print(f"EMA20: {indicators['ema20']:.2f} (Slope: {indicators['ema_slope']:.2f})")
    print(f"VWAP: {indicators['vwap']:.2f}")
    print(f"RVOL: {indicators['rvol']:.2f}")
    print(f"Structure OK: {indicators['structure_ok']}")
    
    # 3. Layer 1 (DNA Gate)
    l1_score, l1_data = intraday_engine._run_layer1(indicators)
    print(f"\n--- 2. LAYER 1 (DNA Gate < 13) ---")
    print(f"L1 Score: {l1_score} / 20")
    for r in l1_data['reasons']: print(f"  └ {r}")
    
    if l1_score < 13:
        print("\n❌ FAILED DNA GATE")
        return
        
    # 4. Layer 2 (Alpha)
    l2_score, l2_data = intraday_engine._run_layer2(indicators, df, df_1h)
    print(f"\n--- 3. LAYER 2 (Alpha Edge) ---")
    print(f"L2 Score: {l2_score} / 60")
    print(f"Alpha Mode: {l2_data['mode']}")
    for r in l2_data['reasons']: print(f"  └ {r}")
    
    # 5. Layer 3 (Safeguards)
    l3_penalty, l3_data = intraday_engine._run_layer3(indicators, df, None, l2_data)
    print(f"\n--- 4. LAYER 3 (Safeguards) ---")
    print(f"L3 Penalty: -{l3_penalty}")
    for r in l3_data['reasons']: print(f"  └ {r}")
    
    final_score = l1_score + l2_score - l3_penalty
    print(f"\n✅ FINAL ENGINE SCORE: {final_score}")

if __name__ == "__main__":
    verify_math()
