import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner

async def verify():
    print("--- Phase 10 Verification ---")
    
    print("Testing Analysis for RELIANCE...")
    res = await scanner.analyze_stock("RELIANCE")
    
    if res:
        print(f"Symbol: {res['symbol']}")
        print(f"Final Score: {res['score']}")
        
        levels = res.get('levels', {})
        resistance = levels.get('resistance', [])
        support = levels.get('support', [])
        
        print("\n[Technical Ladder]")
        print(f"Resistance Levels found: {len(resistance)}")
        for r in resistance:
            print(f"  - {r['label']}: ₹{r['price']} ({r['type']})")
            
        print(f"Support Levels found: {len(support)}")
        for s in support:
            print(f"  - {s['label']}: ₹{s['price']} ({s['type']})")
            
        if len(resistance) > 0 or len(support) > 0:
            print("\nSUCCESS: Phase 10 Technical Ladder data detected.")
        else:
            print("\nFAILURE: No levels found in response.")
    else:
        print("Analysis failed (likely market data fetch error).")

if __name__ == "__main__":
    asyncio.run(verify())
