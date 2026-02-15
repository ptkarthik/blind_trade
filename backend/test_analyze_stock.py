
import asyncio
from app.services.scanner_engine import scanner_engine

async def main():
    print("Analyzing RELIANCE...")
    res = await scanner_engine.analyze_stock("RELIANCE")
    if res:
        print("✅ SUCCESS!")
        print(f"Signal: {res['signal']} | Score: {res['score']}")
        print(f"Target: {res['target']} | Stop: {res['stop_loss']}")
        print(f"Advisor Holding: {res.get('advisor', {}).get('holding_period', {}).get('period_display')}")
        
        import json
        with open("re_test_output.json", "w") as f:
            json.dump(res, f, indent=2)
        print("Result saved to re_test_output.json")
    else:
        print("❌ FAILED: analyze_stock returned None")

if __name__ == "__main__":
    asyncio.run(main())
