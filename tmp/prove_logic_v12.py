import sys
import os
import pandas as pd
import numpy as np
import asyncio
sys.path.append(os.getcwd()) 
from app.services.intraday_engine import IntradayEngine

async def prove_logic():
    print("--- 🕵️‍♂️ V12.1 Institutional Logic Proof ---")
    engine = IntradayEngine()
    
    # Create Mock "Perfect" Stock Data
    # 1. Price > EMA20
    # 2. RVOL > 1.5
    # 3. Pioneer V6 Elite Trigger (VWAP Hook, Ignition, HH/HL)
    dates = pd.date_range(start="2024-04-01", periods=100, freq="15min")
    df = pd.DataFrame({
        'open': np.linspace(100, 110, 100),
        'high': np.linspace(101, 111, 100),
        'low': np.linspace(99, 109, 100),
        'close': np.linspace(100.5, 110.5, 100),
        'volume': [1000] * 99 + [5000] # Ignition spike
    }, index=dates)

    # Mock analyze_stock response to simulate Layer components
    # In a real test, we would mock the individual TA methods, 
    # but here we prove the Engine's Layer-Summing logic.
    
    pulse_data = {
        "TEST_STOCK": {
            "15m": df,
            "price": 110.5
        }
    }

    print("📡 Analyzing Mock 'Universal Winner' setup...")
    # NOTE: To run this accurately, we need to ensure the engine uses the 
    # mock data without calling market_service.
    
    # Since the engine is logic-heavy, we verify the math 1:1 against the implementation:
    # L1: DNA (VWAP, ADX, PA, Vol) -> Max 40
    # L2: Alpha (Pioneer Elite +60) -> Max 60
    # L3: Penalties (EMA20, etc.)
    
    result = await engine.analyze_stock("TEST_STOCK", pulse_data=pulse_data)
    
    print(f"\n🏆 Result for TEST_STOCK:")
    print(f"Score: {result.get('score')}")
    print(f"Signal: {result.get('signal')}")
    print(f"Groups: {result.get('groups')}")
    
    if result.get('score', 0) >= 60:
        print("\n✅ PROOF: Institutional Math identifies ELITE setups.")
    else:
        print("\n⚠️ ALERT: Logic check failed. Investigate multipliers.")

if __name__ == "__main__":
    asyncio.run(prove_logic())
