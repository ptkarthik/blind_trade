import sys
import os
sys.path.append(os.getcwd())

import asyncio
import pandas as pd
from app.services.ta_intraday import IntradayTechnicalAnalysis
from app.services.market_data import market_service

async def debug_stock(sym):
    print(f"--- Debugging {sym} ---")
    df_15m = await market_service.get_ohlc(sym, period="30d", interval="15m")
    live_price = await market_service.get_latest_price(sym)
    if df_15m is None or df_15m.empty:
        print("No data")
        return

    df_15m.attrs["symbol"] = sym
    
    # Run detectors
    ta = IntradayTechnicalAnalysis.analyze_stock(df_15m)
    sweep = IntradayTechnicalAnalysis.detect_stop_hunt_sweep(df_15m)
    structure = IntradayTechnicalAnalysis.detect_market_structure(df_15m)
    trend = IntradayTechnicalAnalysis.detect_trend_direction(df_15m)
    trap = IntradayTechnicalAnalysis.detect_liquidity_trap(df_15m)
    
    print(f"ADX: {ta.get('adx_details', {}).get('adx')}")
    print(f"Trend: {trend.get('trend_direction_state')}")
    print(f"Structure: {structure.get('market_structure_state')}")
    print(f"Sweep Check: {sweep}")
    print(f"Trap Check: {trap.get('trap_move_detected')}")
    
    # Check block conditions from engine (Module 3, 5, 13, 14)
    adx_val = ta.get("adx_details", {}).get("adx", 0)
    fake_breakout = sweep.get("fake_breakout_flag", False)
    
    blocks = []
    if adx_val < 18: blocks.append("Weak ADX")
    if trend.get("trend_direction_state") == "BEARISH_TREND": blocks.append("Bearish Trend")
    if structure.get("market_structure_state") == "BEARISH_STRUCTURE": blocks.append("Bearish Structure")
    if fake_breakout: blocks.append("Failed Breakout Collapse")
    
    print(f"Active Blocks: {blocks}")

if __name__ == "__main__":
    asyncio.run(debug_stock("A2ZINFRA.NS"))
    asyncio.run(debug_stock("AAKASH.NS"))
