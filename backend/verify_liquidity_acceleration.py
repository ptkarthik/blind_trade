import pandas as pd
import numpy as np
import sys
import os
import asyncio

# Add the project root to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mock services
import types
m_ctx = types.ModuleType('app.services.index_context')
m_ctx.index_ctx = {"market_regime": "Mixed", "ad_ratio": 1.0, "market_trend": "Neutral", "score": 50}
sys.modules['app.services.index_context'] = m_ctx

m_market = types.ModuleType('app.services.market_data')
m_market.market_service = types.SimpleNamespace(
    get_sector_for_symbol=lambda x: "IT",
    get_ohlc=lambda *args, **kwargs: pd.DataFrame(),
    get_latest_price=lambda x: 100.0,
    get_sector_densities=lambda: {"IT": 0.5}
)
sys.modules['app.services.market_data'] = m_market

from app.services.intraday_engine import IntradayEngine

async def run_test(v_seq, rvol, label):
    print(f"\n--- Testing: {label} ---")
    engine = IntradayEngine()
    
    # Mock df_15m
    df = pd.DataFrame({
        'open': [99] * 3,
        'high': [101] * 3,
        'low': [98] * 3,
        'close': [100] * 3,
        'volume': v_seq
    })
    df.index = pd.date_range("2023-01-01", periods=3, freq="15min")
    
    # Mock ta_intraday.analyze_stock and other returns
    # We'll need to mock a lot to get analyze_stock to run
    # Alternatively, we test the logic via internal state if possible
    # But analyze_stock is a giant method.
    
    # Let's try to mock enough to reach the logic
    # Actually, simpler to just verify the code structure if full mock is too heavy,
    # but I want to see the score impact.
    
    # Mocking TA result
    mt = types.ModuleType('app.services.ta_intraday')
    mt.ta_intraday = types.SimpleNamespace(
        IntradayTechnicalAnalysis=types.SimpleNamespace(
            analyze_stock=lambda df: {"vwap_score": 100, "pa_score": 100, "pivot_score": 100, "adx_score": 50, "rvol_val": rvol, "vwap_val": 99.0, "adx_details": {}, "fan_bonus": 0},
            detect_stop_hunt_sweep=lambda df: {"liquidity_sweep": False},
            detect_smart_money_accumulation=lambda df: {"accumulation_detected": False},
            detect_market_structure=lambda df: {"market_structure_state": "BULLISH_STRUCTURE"},
            detect_liquidity_trap=lambda df: {"trap_move_detected": False},
            detect_trend_direction=lambda df: {"trend_direction_state": "BULLISH_TREND"}
        ),
        analyze_stock=lambda df: {"ema_score": 100}
    )
    sys.modules['app.services.ta_intraday'] = mt

    # Re-import after mock
    import importlib
    importlib.reload(sys.modules['app.services.intraday_engine'])
    from app.services.intraday_engine import IntradayEngine
    
    # We still need market_service.get_ohlc to return our df
    import app.services.market_data.market_service as ms
    ms.get_ohlc = lambda *args, **kwargs: df
    ms.get_latest_price = lambda x: 100.0
    
    res = await IntradayEngine().analyze_stock("RELIANCE")
    if res:
        print(f"State: {res['liquidity_acceleration_state']}")
        print(f"Sequence: {res['volume_candle_sequence']}")
        print(f"Detected: {res['acceleration_detected']}")
        
        # Check reasons for impact
        for r in res['reasons']:
            if "Liquidity" in r['text'] or "Institutional Ignition" in r['text'] or "Exhaustion" in r['text']:
                print(f"Impact: {r['impact']} ({r['text']})")

async def main():
    # CONFIRMED: V3 > V2 > V1 and V3 >= 1.2 * V2
    await run_test([1000, 1100, 1400], 1.6, "CONFIRMED ACCELERATION")
    
    # WEAK_SPIKE: RVOL > 1.5 but not accel
    await run_test([1000, 1500, 1400], 1.6, "WEAK SPIKE")
    
    # INSTITUTIONAL_IGNITION: Accel + RVOL >= 2.5
    await run_test([1000, 1100, 1400], 2.6, "INSTITUTIONAL IGNITION")
    
    # EXHAUSTION_WARNING: RVOL >= 2.0 but V3 < V2
    await run_test([1000, 1500, 1400], 2.1, "EXHAUSTION WARNING")

if __name__ == "__main__":
    asyncio.run(main())
