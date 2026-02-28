import asyncio
import sys
import os

# Add backend dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine

async def test_single(symbol):
    print(f"Testing Swing logic for: {symbol}")
    result = await swing_engine.analyze_stock(symbol, "test_job")
    
    if result:
         print(f"✅ Match Found for {symbol}")
         print(f"Target: {result.get('target')} | Stop Loss: {result.get('stop_loss')}")
         print(f"Hold: {result.get('hold_duration')}")
         print("Reasons:")
         for r in result['reasons']:
             print(f"  - {r['text']}: {r['value']}")
    else:
         print(f"❌ No swing match for {symbol}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        asyncio.run(test_single(sys.argv[1]))
    else:
        # Just grab random known tickers for testing rules logic 
        asyncio.run(test_single("RELIANCE.NS"))
        asyncio.run(test_single("TCS.NS"))
