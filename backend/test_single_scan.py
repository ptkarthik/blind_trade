import asyncio
import sys
from app.services.intraday_engine import IntradayEngine

async def run_test():
    print("Initializing Intraday Engine...")
    engine = IntradayEngine()
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS"]
    
    for sym in symbols:
        print(f"\n--- Scanning {sym} ---")
        try:
            result = await engine.analyze_stock(sym)
            if result:
                print(f"[{sym}] Verdict: {result.get('verdict')}")
                print(f"[{sym}] Score: {result.get('score')} | Risk: {result.get('alpha_intel', {}).get('risk_level')}")
                print(f"[{sym}] Targets: 1R: {result.get('target_1', 'N/A')} / 2R: {result.get('target')} | SL: {result.get('stop_loss')} | PosSize: {result.get('v6_position_size')}")
                print(f"[{sym}] Tags: {result.get('setup_tag')}")
                if result.get('reasons'):
                    print("--- Reasons ---")
                    for r in result.get('reasons')[:3]:
                        print(f"  {r.get('type')}: {r.get('text')} ({r.get('impact')} pts)")
            else:
                print(f"[{sym}] No valid technical setup or skipped.")
        except Exception as e:
            print(f"[{sym}] ERROR: {e}")

if __name__ == '__main__':
    asyncio.run(run_test())
