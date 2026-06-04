import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine

async def main():
    print("Starting Diagnostic Swing Scan...", flush=True)
    job_id = "test_diag"
    swing_engine.start_job(job_id)
    
    # We will just run the scan. If it errors, we will see it.
    try:
        results = await swing_engine.run_scan(job_id)
        print(f"Returned Data Count: {len(results.get('data', []))}")
        if results.get('data'):
            for t in results['data'][:2]:
                print(f"{t['symbol']} | AI Approved: {t.get('ai_approved')}")
    except Exception as e:
        print(f"CRASH: {e}")

if __name__ == "__main__":
    asyncio.run(main())
