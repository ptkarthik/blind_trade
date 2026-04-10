import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import intraday_engine

async def run():
    print("🚀 Initializing diagnostic scan for RELIANCE.NS, TCS.NS, HDFCBANK.NS...")
    
    # We use a mocked pulse_data with some spoofed bullish indicators, or just run native
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
    
    for sym in symbols:
        res = await intraday_engine.analyze_stock(sym)
        if "skip_reason" in res:
            print(f"⚠️ {sym}: SKIPPED - {res['skip_reason']}")
            continue
            
        l1 = res.get("groups", {}).get("DNA (40%)", {}).get("score", 0)
        l2 = res.get("groups", {}).get("Alpha Edge (60%)", {}).get("score", 0)
        l3 = res.get("groups", {}).get("Safeguards (L3)", {}).get("score", 0)
        
        reasons = res.get("reasons", [])
        catalysts = [r["text"] for r in reasons if r.get("impact", 0) > 0 and r.get("layer") in [1, 2]]
        penalties = [r["text"] for r in reasons if r.get("impact", 0) < 0 and r.get("layer") == 3]
        
        print(f"\n✅ {sym}: {res['score']:>5} | [L1:{l1:>4} | L2:{l2:>4} | L3:{l3:>5}] | {res['signal']} ({res.get('alpha_mode', 'NONE')})")
        if catalysts: print(f"   └ 🚀 Catalysts: {', '.join(catalysts)}")
        if penalties: print(f"   └ 🛡️ Penalties: {', '.join(penalties)}")

if __name__ == "__main__":
    asyncio.run(run())
