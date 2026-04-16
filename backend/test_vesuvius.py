import asyncio
import sys
sys.path.insert(0, '.')

async def run():
    from app.services.swing_engine import swing_engine
    from app.services.market_data import market_service
    
    await market_service.initialize()
    await swing_engine.refresh_market_context()
    
    # Test Vesuvius
    result = await swing_engine.analyze_stock('VESUVIUS.NS')
    if result:
        print(f"\n{'='*60}")
        print(f"VESUVIUS.NS ANALYSIS RESULT")
        print(f"{'='*60}")
        for k, v in result.items():
            print(f"  {k}: {v}")
    else:
        print("VESUVIUS.NS: No match (returned None)")

asyncio.run(run())
