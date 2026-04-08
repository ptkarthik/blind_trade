
import asyncio
import os
import pandas as pd
import sys
import numpy as np

# Absolute path based on user info
sc_path = r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend"
sys.path.append(sc_path)

from app.services.intraday_engine import IntradayEngine
from app.services.market_data import market_service

async def debug_symbol(symbol):
    engine = IntradayEngine()
    
    print(f"--- Debugging {symbol} ---")
    
    # Get Nifty context first
    global_ctx = await engine._get_index_context()
    print(f"Market Context: Regime={global_ctx.get('market_regime')}, AD Ratio={global_ctx.get('ad_ratio')}, Sideways={global_ctx.get('is_sideways')}")
    
    # Analyze stock
    result = await engine.analyze_stock(symbol, global_index_ctx=global_ctx)
    
    if "skip_reason" in result:
        print(f"Skipped: {result['skip_reason']}")
        return

    print(f"Final Score: {result.get('score')}")
    print(f"Signal: {result.get('signal')}")
    print("\nReasoning Breakdown:")
    for r in result.get("reasons", []):
        layer = r.get("layer", "?")
        impact = r.get("impact", 0)
        text = r.get("text", "")
        # Highlight negative impacts
        marker = "❌" if impact < 0 else "✅"
        print(f"  {marker} [Layer {layer}] {text}: {impact}")

if __name__ == "__main__":
    sym = "HDFCBANK.NS"
    if len(sys.argv) > 1:
        sym = sys.argv[1]
    asyncio.run(debug_symbol(sym))
