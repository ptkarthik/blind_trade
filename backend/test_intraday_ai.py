import asyncio
import os
import sys
import json
from unittest.mock import patch
from app.services.intraday_engine import intraday_engine
from app.services.market_discovery import market_discovery
from app.services.ai_brain import ai_brain

async def mock_get_full_market_list():
    return [{"symbol": "PRESTIGE.NS"}, {"symbol": "CARBORUNIV.NS"}]

async def test_ai_gatekeeper():
    print("Testing AI Gatekeeper Integration on PRESTIGE and CARBORUNIV...")
    
    if not ai_brain.is_enabled:
        print("ERROR: AI Brain is disabled! Missing GEMINI_API_KEY")
        return
        
    print(f"Using Model: {ai_brain.model_name}")
    
    # Patch the market discovery to only return our two test symbols
    with patch.object(market_discovery, 'get_full_market_list', new=mock_get_full_market_list):
        job_id = "test-ai-job"
        
        # We need a dummy progress loop task to not crash
        intraday_engine.job_states[job_id] = {"results": [], "progress": 0, "is_running": True, "pause_requested": False}
        
        # Run the scan
        await intraday_engine.run_scan(job_id)
        
        print("\n--- SCAN RESULTS ---")
        results = intraday_engine.job_states[job_id].get("results", [])
        
        for r in results:
            print(f"\nSymbol: {r['symbol']}")
            print(f"Score: {r['score']}")
            print(f"AI Approved: {r.get('ai_approved', 'NOT RUN')}")
            if "ai_reason" in r:
                print(f"AI Reason: {r['ai_reason']}")
                print(f"AI Confidence: {r['ai_confidence']}")
            
            for reason in r.get("reasons", []):
                if "AI REJECTED" in reason.get("text", ""):
                    print(f"-> Found Rejection tag: {reason['text']}")

if __name__ == "__main__":
    asyncio.run(test_ai_gatekeeper())
