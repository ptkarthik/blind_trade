import sys
import os
import io

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

sys.path.append(os.getcwd())

import asyncio
from app.db.session import AsyncSessionLocal
from app.models.job import Job
from sqlalchemy import select

async def main():
    async with AsyncSessionLocal() as session:
        query = select(Job).where(Job.type == 'intraday', Job.status == 'completed').order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(query)
        job = res.scalars().first()
        
        if not job:
            print("No completed intraday job found.")
            return
        
        result = job.result
        items = result.get("data", []) if isinstance(result, dict) else result
        
        print(f"Job: {str(job.id)[:8]} | Updated: {job.updated_at}")
        print(f"System State: {result.get('system_state', {})}")
        print(f"Total results stored: {len(items)}")
        print(f"Total scanned: {result.get('total', '?')} | Passed: {result.get('success', '?')}")
        
        # Score distribution
        scores = [r.get("score", 0) for r in items]
        zero_ct = sum(1 for s in scores if s == 0)
        low_ct = sum(1 for s in scores if 0 < s < 50)
        mid_ct = sum(1 for s in scores if 50 <= s < 65)
        high_ct = sum(1 for s in scores if s >= 65)
        
        print(f"\nScore distribution:")
        print(f"  Zero (0): {zero_ct}")
        print(f"  Low (1-49): {low_ct}")
        print(f"  Mid (50-64): {mid_ct}")
        print(f"  High (65+): {high_ct}")
        
        print(f"\n{'='*80}")
        print(f"ALL {len(items)} RESULTS (sorted by score)")
        print(f"{'='*80}")
        
        for r in sorted(items, key=lambda x: x.get("score", 0), reverse=True):
            sym = r.get("symbol", "?")
            sc = r.get("score", 0)
            sig = r.get("signal", "?")
            mode = r.get("mode", "?")
            groups = r.get("groups", {})
            l1 = groups.get("DNA (40%)", {}).get("score", "?")
            l2 = groups.get("Alpha Edge (60%)", {}).get("score", "?")
            l3 = groups.get("Safeguards (L3)", {}).get("score", "?")
            reasons = r.get("reasons", [])
            
            print(f"\n  {sym:20} Score:{sc:>6.1f} | L1:{l1:>4} L2:{l2:>4} L3:{l3:>5} | Mode:{mode:>20} | Signal:{sig}")
            
            # Show all reasons
            for reason in reasons:
                impact = reason.get("impact", 0)
                layer = reason.get("layer", "?")
                text = reason.get("text", "")
                print(f"    [{impact:>+5}] (L{layer}) {text}")

if __name__ == "__main__":
    asyncio.run(main())
