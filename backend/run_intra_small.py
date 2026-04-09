import asyncio
import pandas as pd
from app.services.intraday_engine import intraday_engine
from app.services.market_data import market_service

async def test_small():
    symbols = ["ZOMATO.NS", "RELIANCE.NS", "TATAMOTORS.NS", "ADANIENT.NS", "HDFCBANK.NS"]
    print(f"Testing Intraday Engine on a small subset: {symbols}")
    
    # We use run_scan but we manually pass the symbols if we can, 
    # but run_scan usually fetches from discovery.
    # Let's bypass run_scan and use analyze_stock directly for these symbols to see the output.
    
    for sym in symbols:
        print(f"\n--- Analyzing {sym} ---")
        try:
            # We need the 15m and 1h data
            df_15m = await market_service.get_ohlc(sym, period="7d", interval="15m")
            df_1h = await market_service.get_ohlc(sym, period="15d", interval="60m")
            
            if df_15m is None or df_15m.empty:
                print(f"No data for {sym}")
                continue
                
            res = await intraday_engine.analyze_stock(sym, pulse_data={sym: {"15m": df_15m, "1h": df_1h}})
            
            print(f"Symbol: {res['symbol']} | Score: {res.get('score', 0)} | Signal: {res.get('signal')}")
            print(f"Layer Breakdown: L1: {res['groups']['DNA (40%)']['score']} | L2: {res['groups']['Alpha Edge (60%)']['score']} | L3: {res['groups']['Safeguards (L3)']['score']}")
            
            reasons = res.get("reasons", [])
            print("Audit Trail:")
            for r in reasons:
                impact = r.get('impact', 0)
                if impact != 0:
                    sign = "+" if impact > 0 else ""
                    print(f"  [{r['layer']}] {r['text']}: {sign}{impact}")
        except Exception as e:
            print(f"Error analyzing {sym}: {e}")

if __name__ == "__main__":
    asyncio.run(test_small())
