
import asyncio
import pandas as pd
from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_verdict(symbol):
    print(f"\n--- Testing Verdict for {symbol} ---")
    try:
        # We need a job_id for the engine state, but for a single stock we can call analyze_stock directly
        res = await scanner_engine.analyze_stock(symbol)
        if res:
            print(f"Score: {res['score']}")
            print(f"Signal: {res['signal']}")
            print(f"Verdict: {res['strategic_summary']}")
            print(f"Rationale: {res['category_rationale']}")
            adv = res.get('investment_advisory', {})
            print(f"Advice Target: {adv.get('targets', {}).get('3_year_target')}")
            print(f"Advice ROI: {adv.get('targets', {}).get('projected_cagr')}%")
        else:
            print("Failed to analyze stock.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import os
    # Ensure we are in the right directory
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_verdict("PTC.NS"))
    loop.run_until_complete(test_verdict("HCLTECH.NS"))
