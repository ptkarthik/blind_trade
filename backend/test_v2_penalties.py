import asyncio
from app.services.swing_engine import swing_engine

async def main():
    print("Testing KSHINTL.NS...")
    res = await swing_engine.analyze_stock("KSHINTL.NS", "test-job-1")
    if res:
        print(f"\nFinal Score: {res['score']}")
        for r in res.get('reasons', []):
            if r.get('impact', 0) < 0:
                print(f"PENALTY: {r['text']} (Impact: {r['impact']})")
            else:
                print(f"BOOST: {r['text']} (Impact: {r['impact']})")
    
    print("\n------------------\n")
    print("Testing FINCABLES.NS...")
    res2 = await swing_engine.analyze_stock("FINCABLES.NS", "test-job-2")
    if res2:
        print(f"\nFinal Score: {res2['score']}")
        for r in res2.get('reasons', []):
            if r.get('impact', 0) < 0:
                print(f"PENALTY: {r['text']} (Impact: {r['impact']})")
            else:
                print(f"BOOST: {r['text']} (Impact: {r['impact']})")

if __name__ == "__main__":
    asyncio.run(main())
