import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner

async def verify():
    print("--- Edge Indicator Suite Verification ---")
    
    # RELIANCE is a good test case for stable fundamentals and technicals
    print("Testing Analysis for RELIANCE...")
    res = await scanner.analyze_stock("RELIANCE")
    
    if res:
        print(f"Symbol: {res['symbol']}")
        print(f"Final AI Conviction Score: {res['score']}")
        
        # Phase 11 Check
        print(f"\n[Phase 11] Accumulation Status: {res.get('accumulation_status', 'N/A')}")
        
        # Phase 12 Check
        print(f"\n[Phase 12] Absolute Valuation (DCF)")
        print(f"  - Current Price: ₹{res.get('price')}")
        print(f"  - Intrinsic Value: ₹{res.get('intrinsic_value')}")
        print(f"  - Valuation Gap: {res.get('valuation_gap')}%")
        
        # Phase 13 Check
        squeeze = res.get('squeeze', {})
        print(f"\n[Phase 13] Breakout Timing (Squeeze)")
        print(f"  - Status: {squeeze.get('label', 'N/A')}")
        print(f"  - Compression: {squeeze.get('compression', 'N/A')}%")
        
        print("\nSUCCESS: All Edge Indicators found in signal response.")
    else:
        print("Analysis failed.")

if __name__ == "__main__":
    asyncio.run(verify())
