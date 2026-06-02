import asyncio
import sys
import os
import traceback

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.ai_brain import ai_brain

async def main():
    print("Testing AI Brain REST call directly...", flush=True)
    try:
        res = await ai_brain.analyze_trade_setup(
            symbol="RELIANCE.NS",
            strategy="BREAKOUT",
            current_price=100.0,
            indicators={"setup_type": "BREAKOUT", "verdict": "Mock", "engine_score": 100},
            engine_reasons=[{"label": "MACD", "value": "Bullish", "text": "MACD Crossover"}]
        )
        print("Result:", res)
    except Exception as e:
        print("CRASH:", e)
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
