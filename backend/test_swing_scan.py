import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine

async def main():
    print("Starting Full Swing Scan with AI Validation...", flush=True)
    # Give it a dummy job id
    job_id = "test_ai_swing"
    
    # We must start the job state before running the scan
    swing_engine.start_job(job_id)
    
    # Run the full scan
    results = await swing_engine.run_scan(job_id)
    
    print("\n\n--- FINAL TRADE PLAN ---")
    if results and "data" in results:
        for trade in results["data"]:
            print(f"\n{trade['symbol']} | Score: {trade['score']} | {trade['setup_type']}")
            print(f"AI Approved: {trade.get('ai_approved')}")
            print(f"AI Confidence: {trade.get('ai_confidence')}")
            print(f"AI Reason: {trade.get('ai_reason')}")
            print("-" * 50)
    else:
        print("No results returned or scan aborted.")

if __name__ == "__main__":
    asyncio.run(main())
