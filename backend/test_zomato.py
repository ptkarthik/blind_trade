
import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.services.scanner_engine import scanner_engine
from app.services.market_data import market_service

async def test_zomato():
    symbol = "ZOMATO"
    print(f"--- Debugging Zomato Analysis ---")
    
    # 1. Test symbol candidates
    candidates = [f"{symbol}.NS", f"{symbol}.BO", symbol]
    
    for sym in candidates:
        print(f"\nChecking Candidate: {sym}")
        try:
            # Check OHLC
            df = await market_service.get_ohlc(sym, period="1y", interval="1d")
            print(f"   OHLC Status: {'✅ Data Found' if not df.empty else '❌ EMPTY'}")
            if not df.empty:
                print(f"   Sample Close: {df['close'].iloc[-1]}")
                
            # Check Live Price
            lp = await market_service.get_live_price(sym)
            print(f"   Live Price: {lp.get('price', 'N/A')} (Source: {lp.get('source', 'N/A')})")
            
            # If we have data, try full analysis
            if not df.empty:
                print(f"   Running Full Analysis...")
                res = await scanner_engine.analyze_stock(sym)
                if res:
                    print(f"   ✅ Analysis Success! Score: {res.get('score')}")
                    # Check for empty values
                    print(f"   Target: {res.get('target')}")
                    print(f"   Stop: {res.get('stop_loss')}")
                    print(f"   Reasons: {len(res.get('reasons', []))}")
                else:
                    print(f"   ❌ Analysis failed for {sym}")
        except Exception as e:
            print(f"   ❌ Error for {sym}: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test_zomato())
