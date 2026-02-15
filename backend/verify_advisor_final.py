
import asyncio
import sys
import os

# Set up paths to import the app
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_verdict(symbol):
    try:
        res = await scanner_engine.analyze_stock(symbol)
        if res:
            signal = res.get('signal')
            score = res.get('score')
            verdict = res.get('strategic_summary')
            advisory = res.get('investment_advisory', {})
            targets = advisory.get('targets', {})
            holding = advisory.get('holding_period', {})
            
            output = f"[{symbol}] Score: {score} | Signal: {signal}\n"
            output += f"Play Type: {holding.get('play_type')}\n"
            output += f"Projected ROI: {targets.get('projected_cagr')}% per year\n"
            output += f"Verdict: {verdict}\n"
            return output
        else:
            return f"Failed to analyze {symbol}\n"
    except Exception as e:
        return f"Error analyzing {symbol}: {e}\n"

async def main():
    await market_service.initialize()
    out1 = await test_verdict("PTC.NS")
    out2 = await test_verdict("HCLTECH.NS")
    with open("verification_final.txt", "w", encoding="utf-8") as f:
        f.write(out1)
        f.write("\n")
        f.write(out2)

if __name__ == "__main__":
    asyncio.run(main())
