
import asyncio
import pandas as pd
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine

async def verify_institutional_suite():
    print("--- Professional Upgrade Suite: End-to-End Verification ---")
    
    # We test analyze_stock directly with mock data
    symbol = "TCS"
    
    # We pass mock weights and macro data as if Scanner did the detection
    weights = {
        "fundamental": 0.50, # BEAR weighting
        "trend": 0.15,
        "momentum": 0.05,
        "volume": 0.15,
        "risk": 0.15
    }
    macro_data = {
        "label": "High Crude (Energy Headwinds)",
        "crude": 95,
        "currency": 83.2
    }
    
    print(f"Testing {symbol} with BEAR Regime and HIGH CRUDE macro...")
    
    # Note: analyze_stock will fetch real data from yfinance if we don't mock the service.
    # For a fast test, we just check if it executes without error.
    try:
        res = await scanner_engine.analyze_stock(symbol, weights=weights, regime_label="Bearish", macro_data=macro_data)
        
        if res:
            print(f"Success! Score: {res['score']} | Signal: {res['signal']}")
            print(f"Regime: {res['weights']['regime']}")
            print(f"Moat: {res['alpha_intel']['moat_status']}")
            print(f"Recovery: {res['alpha_intel']['recovery_vibe']}")
            
            # Assertions
            assert res['weights']['regime'] == "Bearish"
            assert res['weights']['Fundamental'] == 50
            
            print("\n✅ Verification Passed: Adaptive Engine correctly applied Bearish weighting.")
        else:
            print("❌ Verification Failed: Engine returned None (possible API failure).")
            
    except Exception as e:
        print(f"❌ Verification Failed with error: {e}")

if __name__ == "__main__":
    asyncio.run(verify_institutional_suite())
