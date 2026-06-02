import sys, os, asyncio
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine
from app.services.market_data import market_service
from app.services.kite_data import kite_data

async def main():
    print("Initializing...")
    await kite_data.initialize()
    await market_service.initialize()
    await swing_engine.refresh_market_context()
    
    print("\nAnalyzing INFOBEAN.NS...")
    res1 = await swing_engine.analyze_stock("INFOBEAN.NS")
    if res1:
        print(f"INFOBEAN Score: {res1.get('score')} | Strategy: {res1.get('strategy')}")
        print("Reasons:")
        for r in res1.get('reasons', []):
            print(f" - {r.get('text')}")
    else:
        print("INFOBEAN: No Match")

    print("\nAnalyzing ACMESOLAR.NS...")
    res2 = await swing_engine.analyze_stock("ACMESOLAR.NS")
    if res2:
        print(f"ACMESOLAR Score: {res2.get('score')} | Strategy: {res2.get('strategy')}")
        print("Reasons:")
        for r in res2.get('reasons', []):
            print(f" - {r.get('text')}")
    else:
        print("ACMESOLAR: No Match")

if __name__ == "__main__":
    asyncio.run(main())
