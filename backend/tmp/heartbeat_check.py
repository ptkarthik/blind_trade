import asyncio
import os
import sys
# Ensure we're in the right python path
sys.path.append(os.getcwd())

async def audit():
    from app.services.intraday_engine import IntradayEngine
    from app.services.market_service import market_service
    import pandas as pd
    
    engine = IntradayEngine()
    test_syms = ["WIPRO.NS", "INFY.NS", "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS"]
    
    print(f"🛰️ AUDITING BATCH DATA FETCH FOR: {test_syms}")
    res_15m = await market_service.get_batch_ohlc(test_syms)
    res_prices = await market_service.get_batch_prices(test_syms)
    print(f"📡 DATA RECEIVED FOR {len(res_15m)} SYMBOLS")
    
    for s in test_syms:
        df = res_15m.get(s)
        if df is None or df.empty:
            print(f"❌ {s}: NO DATA FOUND")
            continue
        
        print(f"🔍 ANALYZING {s} (Length: {len(df)})")
        price = res_prices.get(s, {}).get("price", df['close'].iloc[-1])
        batch_pulse = {s: {"15m": df, "price": price}}
        
        # Test the analysis logic directly
        res = await engine.analyze_stock(s, "diagnostic_job", {}, batch_pulse)
        if "skip_reason" in res:
             print(f"⚠️ {s} SKIPPED: {res['skip_reason']}")
        else:
             print(f"✅ {s} RESULT: Score={res.get('score')}, Signal={res.get('signal')}")

if __name__ == "__main__":
    asyncio.run(audit())
