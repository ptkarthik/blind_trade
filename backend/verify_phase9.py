import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner

async def verify():
    print("--- Phase 9 Verification ---")
    
    # Mock some data if needed or just run a single analysis
    # Let's try to analyze a well known stock like RELIANCE
    print("Testing Analysis for RELIANCE...")
    res = await scanner.analyze_stock("RELIANCE")
    
    if res:
        print(f"Symbol: {res['symbol']}")
        print(f"Final Score: {res['score']}")
        print(f"Strategic Summary: {res.get('strategic_summary')}")
        print(f"Weights: {res.get('weights')}")
        
        # Check for weights integrity
        weights = res.get('weights', {})
        total_weight = sum(weights.values())
        print(f"Total Weight Check: {total_weight}% (Expected 100%)")
        
        if 'strategic_summary' in res and 'weights' in res:
            print("\nSUCCESS: Phase 9 Backend fields detected.")
        else:
            print("\nFAILURE: Missing strategic_summary or weights.")
    else:
        print("Analysis failed (likely market data fetch error).")

if __name__ == "__main__":
    asyncio.run(verify())
