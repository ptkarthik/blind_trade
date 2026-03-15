import asyncio
import os
import sys

# Ensure backend path is available
sys.path.append(os.getcwd())

from app.services.intraday_engine import intraday_engine

async def verify_specialist_fields():
    print("\n🔍 --- Specialist Fields Verification --- 🔍")
    
    symbol = "RELIANCE.NS"
    print(f"Analyzing {symbol} for field verification...")
    
    res = await intraday_engine.analyze_stock(symbol, fast_fail=True)
    if not res:
        print("❌ Analysis failed or skipped.")
        return

    print(f"\n[Basic Info]")
    print(f"Signal: {res.get('signal')}")
    print(f"Score: {res.get('score')}")
    print(f"Logic Type: {res.get('logic_type')}")
    
    print(f"\n[Reasons & Impact]")
    has_impact = False
    for r in res.get('reasons', []):
        impact = r.get('impact')
        if impact is not None:
            has_impact = True
            print(f" - {r.get('text')}: {impact} pts ({r.get('type')})")
    
    if has_impact:
        print("✅ Impact fields found in reasons.")
    else:
        print("⚠️ No impact fields found (might be no active guards right now).")

    print("\n🎉 Verification Pulse Complete.")

if __name__ == "__main__":
    asyncio.run(verify_specialist_fields())
