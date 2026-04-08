
import asyncio
import pandas as pd
import json
from app.services.intraday_engine import IntradayEngine
from app.services.market_data import market_service
import pytz
from datetime import datetime

async def audit_stock_scoring(symbol):
    engine = IntradayEngine()
    print(f"\n🔍 [DEEP AUDIT] Analyzing {symbol} in Intraday Engine...")
    
    # 1. Fetch Index Context (Nifty)
    index_ctx = await engine._get_index_context()
    print(f"🌍 Market Context: {json.dumps(index_ctx, indent=2)}")
    
    # 2. Fetch Stock Data
    df_15m = await market_service.get_ohlc(symbol, period="3d", interval="15m")
    if df_15m is None or df_15m.empty:
        print(f"❌ No data for {symbol}")
        return

    price_info = await market_service.get_live_price(symbol)
    real_price = price_info.get("price", 0.0)
    print(f"💰 Real Price: {real_price}")

    # 3. Step-by-Step Analysis
    res = await engine.analyze_stock(symbol, global_index_ctx=index_ctx)
    
    if res:
        print(f"\n📊 RAW SCORE: {res['score']} | SIGNAL: {res['signal']}")
        print(f"--------------------------------------------------")
        print(f"LAYER-BY-LAYER BREAKDOWN:")
        
        reasons = res.get("reasons", [])
        
        # Layer 1 Audit
        l1_reasons = [r for r in reasons if r.get("layer") == 1]
        l1_sum = sum(r.get("impact", 0) for r in l1_reasons)
        print(f"\n🧬 LAYER 1 (DNA) - Total: {l1_sum:.1f}")
        for r in l1_reasons:
            print(f"  [{r.get('type','').upper():>8}] {r.get('text',''):<30} | Impact: {r.get('impact', 0):>+5.1f}")
            
        # Layer 2 Audit
        l2_reasons = [r for r in reasons if r.get("layer") == 2]
        l2_sum = sum(r.get('impact', 0) for r in l2_reasons)
        print(f"\n🚀 LAYER 2 (ALPHA) - Total: {l2_sum:.1f}")
        for r in l2_reasons:
            print(f"  [{r.get('type','').upper():>8}] {r.get('text',''):<30} | Impact: {r.get('impact', 0):>+5.1f}")
            
        # Layer 3 Audit
        l3_reasons = [r for r in reasons if r.get("layer") == 3]
        l3_sum = sum(r.get('impact', 0) for r in l3_reasons)
        print(f"\n🛡️ LAYER 3 (GUARDS) - Total: {l3_sum:.1f}")
        for r in l3_reasons:
            print(f"  [{r.get('type','').upper():>8}] {r.get('text',''):<30} | Impact: {r.get('impact', 0):>+5.1f}")
            
        print(f"\n🎯 FINAL MATH: {l1_sum:.1f} (L1) + {l2_sum:.1f} (L2) + {l3_sum:.1f} (L3) = {l1_sum + l2_sum + l3_sum:.1f}")
        print(f"   CLAMPED SCORE: {res['score']}")
    else:
        print("❌ Analysis returned None")

if __name__ == "__main__":
    symbol = "20MICRONS.NS" # From screenshot
    asyncio.run(audit_stock_scoring(symbol))
