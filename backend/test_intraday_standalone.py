import asyncio
import time
from app.services.intraday_engine import intraday_engine
from app.services.liquidity_service import liquidity_service

async def test_intraday_analysis():
    symbol = "ZOMATO.NS"
    print(f"Testing Intraday Analysis for {symbol}...")
    
    # Ensure liquidity is bootstrapped
    await liquidity_service.bulk_bootstrap(["ZOMATO.NS", "RELIANCE.NS"])
    
    start = time.time()
    try:
        # Call analyze_stock directly
        res = await intraday_engine.analyze_stock(symbol)
        end = time.time()
        print(f"Analysis Finished in {end-start:.2f}s\n")
        
        if res:
            print("--- INTRADAY ENGINE PAYLOAD ---")
            for k, v in res.items():
                if k == "reasons":
                    print("reasons:")
                    for r in v:
                        print(f"  - [{r.get('impact')}] {r.get('text')}")
                else:
                    print(f"{k}: {v}")
        else:
            print(f"Result for {symbol}: None (Data probably missing)")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Analysis Crashed: {e}")

if __name__ == "__main__":
    asyncio.run(test_intraday_analysis())
