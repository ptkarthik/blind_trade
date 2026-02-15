
import asyncio
import sys
import os
import traceback

sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def find_tactical_play(symbols):
    print(f"--- Searching for Tactical Plays in {len(symbols)} stocks ---")
    for sym in symbols:
        try:
            res = await scanner_engine.analyze_stock(sym)
            if res:
                verdict = res.get('strategic_summary', '')
                if "[🔥 TACTICAL]" in verdict:
                    print(f"\n✅ FOUND TACTICAL PLAY: {sym}")
                    print(f"Verdict: {verdict}")
                    return True
        except Exception:
            print(f"\n❌ Error analyzing {sym}:")
            traceback.print_exc()
    return False

async def main():
    await market_service.initialize()
    # Test with some known momentum stocks
    stocks = ["TATAMOTORS.NS", "IREDA.NS", "RVNL.NS", "ZOMATO.NS", "ADANIPORTS.NS"]
    found = await find_tactical_play(stocks)
    if not found:
        print("\nNo tactical breakout found in sample.")

if __name__ == "__main__":
    asyncio.run(main())
