
import asyncio
import sys
import os

# Set up paths to import the app
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_verdict(symbol):
    print(f"\n--- VERIFICATION: {symbol} ---")
    try:
        res = await scanner_engine.analyze_stock(symbol)
        if res:
            signal = res.get('signal')
            score = res.get('score')
            verdict = res.get('strategic_summary')
            advisory = res.get('investment_advisory', {})
            targets = advisory.get('targets', {})
            holding = advisory.get('holding_period', {})
            
            print(f"[{symbol}] Score: {score} | Signal: {signal}")
            print(f"Play Type: {holding.get('play_type')}")
            print(f"Projected ROI: {targets.get('projected_cagr')}% per year")
            print(f"Verdict Snippet: {verdict}")
        else:
            print(f"Failed to analyze {symbol}")
    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

async def main():
    # Warm up cache
    await market_service.initialize()
    await test_verdict("PTC.NS")
    await test_verdict("HCLTECH.NS")

if __name__ == "__main__":
    asyncio.run(main())
