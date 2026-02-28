import asyncio
import sys
import os

# Add backend dir to python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine

async def main():
    print("Testing Updated Swing Logic...")
    fake_job_id = "test_swing_job_123"
    try:
        result = await swing_engine.run_scan(fake_job_id)
        if result and "data" in result:
            print(f"Swing Scan completed. Found {len(result['data'])} setups.")
            for hit in result['data']:
                print(f"\n--- {hit['symbol']} ---")
                print(f"   Name: {hit['name']}")
                print(f"   Entry: {hit['entry']}")
                print(f"   Target: {hit.get('target')}    | Secondary: {hit.get('secondary_target')}")
                print(f"   Stop: {hit.get('stop_loss')}")
                print(f"   Reasons:")
                for r in hit['reasons']:
                     print(f"      - {r['text']} : {r['value']}")
        else:
            print("Scan completed but no data returned.")
    except Exception as e:
        print(f"Test Failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
