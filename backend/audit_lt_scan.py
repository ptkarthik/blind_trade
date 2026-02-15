
import asyncio
import json
import os
import logging
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.job import Job

# Force suppress ALL logging
logging.getLogger('sqlalchemy').setLevel(logging.ERROR)

async def audit():
    async with AsyncSessionLocal() as session:
        stmt = select(Job).where(Job.type.in_(['full_scan', 'longterm']), Job.status == 'completed').order_by(Job.updated_at.desc()).limit(1)
        res = await session.execute(stmt)
        job = res.scalars().first()
        
        if not job:
            return {"error": "No completed full scan found."}
            
        data = job.result.get('data', [])
        if not data:
            return {"error": "No data in job results."}
            
        scores = [float(x.get('score', 0)) for x in data]
        verdicts = [x.get('verdict', 'N/A') for x in data]
        
        verdict_counts = {}
        for v in verdicts:
            verdict_counts[v] = verdict_counts.get(v, 0) + 1
            
        # Top 10 by score
        data.sort(key=lambda x: x.get('score', 0), reverse=True)
        top_10 = []
        for item in data[:10]:
            top_10.append({
                "symbol": item.get('symbol'),
                "score": item.get('score'),
                "verdict": item.get('verdict'),
                "rationale": item.get('rationale', 'N/A'),
                "trend_score": item.get('trend_score'),
                "is_bullish": "Bullish" in str(item.get('reasons', [])) or "Bull" in str(item.get('reasons', []))
            })

        audit_res = {
            "job_id": str(job.id),
            "total_symbols": len(data),
            "max_score": max(scores) if scores else 0,
            "min_score": min(scores) if scores else 0,
            "avg_score": sum(scores)/len(scores) if scores else 0,
            "verdict_dist": verdict_counts,
            "top_10": top_10
        }
        
        with open("last_scan_audit.json", "w") as f:
            json.dump(audit_res, f, indent=2)
        
        return audit_res

if __name__ == "__main__":
    asyncio.run(audit())
    print("DONE_AUDIT")
