import sys
import os
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime

# Adjust path to import from backend
sys.path.append(os.path.join(os.getcwd()))

async def test_logic():
    print("--- Local Intraday Logic Verification ---")
    
    # Provide 10 candles
    # To trigger BEARISH_STRUCTURE, we need Lower High AND Lower Low
    data = {
        'open':  [100]*10,
        'high':  [105, 106, 107, 108, 109, 110, 111, 112, 110, 109], 
        'low':   [95, 96, 97, 98, 99, 100, 101, 102, 101, 98],     # index 9 low (98) < min(index 4-8) (99)
        'close': [102]*10,
        'volume':[1000]*10
    }
    df = pd.DataFrame(data)
    
    from app.services.ta_intraday import IntradayTechnicalAnalysis
    
    # 1. Test TA Market Structure
    res_ta = IntradayTechnicalAnalysis.detect_market_structure(df)
    print(f"Market Structure State: {res_ta['market_structure_state']}")
    
    assert res_ta['market_structure_state'] == "BEARISH_STRUCTURE", "Should now be bearish with BOTH LH/LL"
    
    print("\n--- TEST PASSED: Technical logic correctly identifies Bearish Structure with LH/LL. ---")

if __name__ == "__main__":
    asyncio.run(test_logic())
