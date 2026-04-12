import sys
import pandas as pd
import numpy as np
import asyncio

sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.services.intraday_engine import intraday_engine
from app.services.liquidity_service import liquidity_service

async def verify_math():
    print("--- 🧪 INTRADAY ENGINE MATH VERIFICATION (V12.9) ---")
    
    symbol = "RELIANCE.NS"
    # Seed mock liquidity data for RELIANCE.NS (High liquidity)
    liquidity_service.liquidity_data[symbol] = {
        "adv20": 5000000,
        "level": "High",
        "last_updated": 0
    }
    
    # 1. Setup a clean, strongly trending dataframe
    dates = pd.date_range("2026-04-10 09:15", periods=50, freq="15min")
    df = pd.DataFrame(index=dates)
    df.attrs["symbol"] = symbol
    df['open'] = np.linspace(100, 110, 50)
    df['high'] = df['open'] + 1
    df['low'] = df['open'] - 0.5
    df['close'] = df['open'] + 0.8
    # Trigger RVOL > 2.0
    vols = [1000] * 48 + [150000, 200000] 
    df['volume'] = vols
    
    # Analyze
    res = await intraday_engine.analyze_stock(symbol, pulse_data={symbol: df})
    
    print("\n--- 1. ANALYSIS RESULTS ---")
    print(f"Symbol: {res['symbol']}")
    print(f"Price: {res['price']}")
    print(f"Score: {res['score']} | Signal: {res['signal']}")
    print(f"Alpha Mode: {res['alpha_mode']}")
    
    print("\n--- 2. LIQUIDITY METRICS ---")
    liq = res['liquidity']
    print(f"Level: {liq['level']}")
    print(f"ADV20: {liq['adv20']:,}")
    print(f"Max Stealth Buy Qty: {liq['max_stealth_buy_qty']:,} shares")
    print(f"Max Stealth Buy Value: ₹{liq['max_stealth_buy_value']:,}")
    
    print("\n--- 3. SAFEGUARDS (L3) ---")
    l3_details = res['groups']['Safeguards (L3)']['details']
    for d in l3_details:
        print(f"  └ {d['text']}: {d['impact']}")

    # Test Illiquid Scrip Penalty
    print("\n--- 4. TESTING ILLIQUID PENALTY ---")
    symbol_low = "PENNY.NS"
    liquidity_service.liquidity_data[symbol_low] = {
        "adv20": 50000, # Below 100k
        "level": "Very Low",
        "last_updated": 0
    }
    df_low = df.copy()
    df_low.attrs["symbol"] = symbol_low
    
    res_low = await intraday_engine.analyze_stock(symbol_low, pulse_data={symbol_low: df_low})
    p_reasons = [r['text'] for r in res_low['reasons'] if "Illiquid" in r['text']]
    if p_reasons:
        print(f"✅ Penalty Detected: {p_reasons[0]}")
    else:
        print("❌ Penalty NOT Detected (Check ADV threshold logic)")

if __name__ == "__main__":
    asyncio.run(verify_math())
