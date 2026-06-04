"""Quick diagnostic: Test intraday scan startup to find where it hangs."""
import sys, os, asyncio
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
sys.path.insert(0, os.getcwd())

import time

async def diagnose():
    print(f"[{time.strftime('%H:%M:%S')}] Step 1: Importing market_discovery...", flush=True)
    from app.services.market_discovery import market_discovery
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 2: Getting market list...", flush=True)
    symbols = await market_discovery.get_full_market_list()
    print(f"[{time.strftime('%H:%M:%S')}] Step 2 DONE: {len(symbols)} symbols", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 3: Importing liquidity_service...", flush=True)
    from app.services.liquidity_service import liquidity_service
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 4: liquidity_service.initialize()...", flush=True)
    await liquidity_service.initialize()
    print(f"[{time.strftime('%H:%M:%S')}] Step 4 DONE", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 5: Importing kite_service...", flush=True)
    from app.services.kite_service import kite_service
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 6: kite_service.initialize()...", flush=True)
    await kite_service.initialize()
    print(f"[{time.strftime('%H:%M:%S')}] Step 6 DONE", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 7: kite_data.initialize()...", flush=True)
    from app.services.kite_data import kite_data
    await kite_data.initialize()
    print(f"[{time.strftime('%H:%M:%S')}] Step 7 DONE: is_ready={kite_data.is_ready}", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 8: bulk_bootstrap first 200 symbols...", flush=True)
    first_200 = [s["symbol"] if isinstance(s, dict) else s for s in symbols[:200]]
    await liquidity_service.bulk_bootstrap(first_200)
    print(f"[{time.strftime('%H:%M:%S')}] Step 8 DONE", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 9: Importing intraday_engine...", flush=True)
    from app.services.intraday_engine import intraday_engine
    print(f"[{time.strftime('%H:%M:%S')}] Step 9 DONE", flush=True)
    
    print(f"[{time.strftime('%H:%M:%S')}] Step 10: Getting index context...", flush=True)
    ctx = await intraday_engine._get_index_context()
    print(f"[{time.strftime('%H:%M:%S')}] Step 10 DONE: {ctx}", flush=True)
    
    print(f"\n=== ALL STEPS PASSED === Intraday engine is healthy!", flush=True)

asyncio.run(diagnose())
