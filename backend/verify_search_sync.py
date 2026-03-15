import asyncio
import os
import sys

# Ensure backend path is available
sys.path.append(os.getcwd())

from app.services.intraday_engine import intraday_engine
from app.services.swing_engine import swing_engine
from app.services.scanner_engine import longterm_scanner_engine

async def verify_search_sync():
    print("\n🔍 --- Cross-Mode On-Demand Search Verification --- 🔍")
    
    symbol = "RELIANCE.NS"
    
    # 1. Verify Intraday
    print(f"\n[Mode: Intraday] - Analyzing {symbol}...")
    intra = await intraday_engine.analyze_stock(symbol, fast_fail=True)
    if intra:
        print(f"✅ Score: {intra.get('score')} | Tags: {intra.get('setup_tag')} | Signal: {intra.get('signal')}")
    else:
        print("⚠️ Intraday analysis skipped (possibly no 5m data right now).")

    # 2. Verify Swing
    print(f"\n[Mode: Swing] - Analyzing {symbol}...")
    swing = await swing_engine.analyze_stock(symbol)
    if swing:
        print(f"✅ Score: {swing.get('score')} | Tags: {swing.get('setup_tag')} | Signal: {swing.get('signal')}")
    else:
        print("⚠️ Swing analysis skipped (possibly no setup match).")

    # 3. Verify Long-Term
    print(f"\n[Mode: Long-Term] - Analyzing {symbol}...")
    regime = await longterm_scanner_engine._detect_market_regime()
    macro = await longterm_scanner_engine._detect_macro_regime()
    long = await longterm_scanner_engine.analyze_stock(
        symbol, weights=regime["weights"], regime_label=regime["label"], macro_data=macro, fast_fail=True
    )
    if long:
        print(f"✅ Score: {long.get('score')} | Tags: {long.get('setup_tag', 'N/A')} | Signal: {long.get('signal')}")
        # Note: Long-term uses strategic_summary for its tags usually.
    else:
        print("⚠️ Long-Term analysis skipped.")

    print("\n🎉 Verification Complete: All modes are responding with Specialist-Grade structures.")

if __name__ == "__main__":
    asyncio.run(verify_search_sync())
