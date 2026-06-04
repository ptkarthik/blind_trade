import sys
import os
import io

# Prevent Unicode errors on Windows terminal
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.getcwd())

import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select
import json

async def main():
    async with AsyncSessionLocal() as session:
        # Get the latest 10 completed intraday jobs
        query = select(Job).where(Job.type == 'intraday', Job.status == 'completed').order_by(Job.updated_at.desc()).limit(10)
        res = await session.execute(query)
        latest_jobs = res.scalars().all()
        
        if not latest_jobs:
            print("No completed intraday jobs found.")
            return
            
        found_apollo = False
        found_aplltd = False
        
        for latest_job in latest_jobs:
            results = latest_job.result
            if not results:
                continue
                
            items = results if isinstance(results, list) else results.get("results", [])
        
        found_apollo = False
        found_aplltd = False
        
        for r in items:
            sym = r.get("symbol")
            if sym in ["APOLLO.NS", "APLLTD.NS"]:
                print(f"\n{'='*50}")
                print(f"STOCK: {sym}")
                print(f"SCORE: {r.get('score')} | SIGNAL: {r.get('signal')}")
                print(f"{'='*50}")
                
                print("\n[ GROUPS ]")
                groups = r.get("groups", {})
                for g_name, g_data in groups.items():
                    print(f"  {g_name}: {g_data.get('score', 0)}")
                
                print("\n[ EXACT POINT BREAKDOWN (REASONS) ]")
                reasons = r.get("reasons", [])
                if not reasons:
                    print("  No reasons listed.")
                for reason in reasons:
                    impact = reason.get("impact", 0)
                    layer = reason.get("layer", "?")
                    text = reason.get("text", "")
                    
                    if impact > 0:
                        print(f"  ✅ +{impact:<4} (L{layer}) {text}")
                    elif impact < 0:
                        print(f"  ❌ {impact:<5} (L{layer}) {text}")
                    else:
                        print(f"  ℹ️  {impact:<4} (L{layer}) {text}")
                        
                if sym == "APOLLO.NS": found_apollo = True
                if sym == "APLLTD.NS": found_aplltd = True
                
        if not found_apollo: print("\nAPOLLO.NS not found in this job.")
        if not found_aplltd: print("APLLTD.NS not found in this job.")

if __name__ == "__main__":
    asyncio.run(main())
