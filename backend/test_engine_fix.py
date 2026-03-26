import asyncio
import pandas as pd
import numpy as np
import sys
import os

# Add the current directory to sys.path so 'app' can be found
sys.path.append(os.getcwd())

from app.services.intraday_engine import IntradayEngine

async def test_engine_fix():
    print("🚀 Testing Intraday Engine Fix with Mock Data...")
    engine = IntradayEngine()
    
    # Mock data
    symbol = "RELIANCE.NS"
    dates = pd.date_range("2026-03-23 09:15", periods=100, freq="15min", tz='Asia/Kolkata')
    df = pd.DataFrame({
        "open": np.linspace(2500, 2550, 100),
        "high": np.linspace(2510, 2560, 100),
        "low": np.linspace(2490, 2540, 100),
        "close": np.linspace(2505, 2555, 100),
        "volume": np.random.randint(10000, 50000, 100)
    }, index=dates)
    
    # Mock Index Context
    mock_index_ctx = {
        "market_regime": "Strong Bullish",
        "day_change_pct": 1.5,
        "sector_densities": {"Energy": 0.5},
        "sector_perfs": {"Energy": 2.0},
        "delivery_ratio": 60
    }

    # Monkeypatch market_service to return our mock data
    from app.services.market_data import market_service
    
    async def mock_get_ohlc(*args, **kwargs):
        return df
        
    async def mock_get_latest_price(*args, **kwargs):
        return 2555.0
        
    market_service.get_ohlc = mock_get_ohlc
    market_service.get_latest_price = mock_get_latest_price
    market_service.get_live_price = mock_get_latest_price
    
    print(f"Running analyze_stock for {symbol}...")
    try:
        # This is where it used to fail with UnboundLocalError
        res = await engine.analyze_stock(symbol, global_index_ctx=mock_index_ctx)
        if res:
            print(f"✅ SUCCESS! Results obtained.")
            print(f"Score: {res.get('score')}")
            print(f"Target: {res.get('target')}")
            print(f"Stop Loss: {res.get('stop_loss')}")
        else:
            print("❌ FAILED: Analysis returned None")
    except UnboundLocalError as e:
        print(f"❌ FAILED: UnboundLocalError still present: {e}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ FAILED: Unexpected error: {e}")

if __name__ == "__main__":
    asyncio.run(test_engine_fix())
