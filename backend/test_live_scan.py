import asyncio
import sys
import os

# Add project root to sys.path
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")

from app.services.intraday_engine import IntradayEngine

async def test_live_scan():
    engine = IntradayEngine()
    symbols = ["RELIANCE.NS", "ZOMATO.NS", "HDFCBANK.NS", "TATASTEEL.NS", "ITC.NS"]
    
    print(f"🚀 Starting test scan for: {symbols}")
    results = []
    for s in symbols:
        res = await engine.analyze_stock(s)
        results.append(res)
    
    print("\n" + "="*50)
    print("INTRADAY SCAN RESULTS AUDIT")
    print("="*50)
    
    for res in results:
        sym = res.get("symbol")
        if "skip_reason" in res:
            print(f"❌ {sym}: SKIPPED ({res['skip_reason']})")
            continue
            
        score = res.get("score", 0)
        signal = res.get("signal", "IGNORE")
        l1 = res["groups"]["DNA (40%)"]["score"]
        l2 = res["groups"]["Alpha Edge (60%)"]["score"]
        l3 = res["groups"]["Safeguards (L3)"]["score"]
        dna_mode = res.get("dna_mode", "N/A")
        alpha_mode = res.get("alpha_mode", "N/A")
        
        print(f"✅ {sym}: {score} | [{signal}]")
        print(f"   └ DNA: {l1} ({dna_mode}) | Alpha: {l2} ({alpha_mode}) | Safe: {l3}")
        
        if l2 > 0:
            print(f"   🔥 Layer 2 ACTIVATED!")
            for detail in res["groups"]["Alpha Edge (60%)"]["details"]:
                print(f"      - {detail['text']}: +{detail['impact']}")
        else:
            print(f"   ⚠️ Layer 2 ZERO. Diagnostics:")
            for detail in res["groups"]["Alpha Edge (60%)"]["details"]:
                if detail.get('impact', 0) == 0:
                    print(f"      - {detail['text']}")

if __name__ == "__main__":
    asyncio.run(test_live_scan())
