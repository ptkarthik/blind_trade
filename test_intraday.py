import asyncio
import json
from app.services.intraday_engine import intraday_engine

async def run_test():
    symbols = ["RELIANCE.NS", "ZOMATO.NS", "SUZLON.NS", "HDFCBANK.NS"]
    print("Starting Intraday Engine Dry-Run Test...")
    
    # Needs index context
    idx_ctx = await intraday_engine._get_index_context()
    print(f"Index Context: {idx_ctx.get('market_regime')} | Trend: {idx_ctx.get('market_trend')}\n")
    
    for sym in symbols:
        print(f"Analyzing {sym}...")
        try:
            res = await intraday_engine.analyze_stock(sym, global_index_ctx=idx_ctx)
            if "skip_reason" in res:
                print(f"  [{sym}] SKIPPED: {res['skip_reason']}")
                continue
                
            print(f"  [{sym}] SIGNAL: {res['signal_label']} (Score: {res['score']}) | Mode: {res['alpha_mode']}")
            groups = res.get("groups", {})
            for g_name, g_data in groups.items():
                print(f"    - {g_name}: {g_data.get('score')} pts")
                for detail in g_data.get("details", []):
                    print(f"      * {detail.get('text')} ({detail.get('impact')} pts)")
                    
            print(f"  [METRICS] Entry: {res.get('entry')} | Target: {res.get('target')} | SL: {res.get('stop_loss')}")
            print("-" * 50)
        except Exception as e:
            print(f"  [{sym}] ERROR: {str(e)}")

if __name__ == "__main__":
    asyncio.run(run_test())
