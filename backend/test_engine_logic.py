import sys
import os
import asyncio

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.getcwd())
from app.services.intraday_engine import intraday_engine
from app.services.market_data import market_service
from app.services.liquidity_service import liquidity_service

async def manual_test():
    symbols = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ZOMATO.NS", "SUZLON.NS"]
    print(f"Testing new Intraday Engine logic on: {symbols}", flush=True)
    
    await liquidity_service.initialize()
    await liquidity_service.bulk_bootstrap(symbols)
    
    index_ctx = await intraday_engine._get_index_context()
    
    # Simulate the NEW fix for batch fetching!
    try:
        res_15m, res_1h, res_prices = await asyncio.wait_for(
            asyncio.gather(
                market_service.get_batch_ohlc(symbols, interval="15m", period="7d"),
                market_service.get_batch_ohlc(symbols, interval="60m", period="15d"),
                market_service.get_batch_prices(symbols)
            ),
            timeout=120.0
        )
        print("✅ Batch Fetching (15m + 60m) Successful!", flush=True)
    except Exception as e:
        print(f"❌ Batch Fetching failed: {e}", flush=True)
        return
        
    batch_pulse = {}
    for s in symbols:
        batch_pulse[s] = {"15m": res_15m.get(s), "1h": res_1h.get(s), "price": res_prices.get(s, {}).get("price", 0.0)}

    for sym in symbols:
        res = await intraday_engine.analyze_stock(sym, "TEST_JOB", index_ctx, batch_pulse)
        if "skip_reason" in res:
             print(f"⏭️ {sym}: Skipped ({res['skip_reason']})", flush=True)
        else:
             print(f"✅ {sym}: Score={res['score']} | {res['signal']} | RVOL/Turnover logic processed. | L1:{res['groups']['DNA (40%)']['score']} | L2:{res['groups']['Alpha Edge (60%)']['score']} | L3:{res['groups']['Safeguards (L3)']['score']}", flush=True)

if __name__ == "__main__":
    asyncio.run(manual_test())
