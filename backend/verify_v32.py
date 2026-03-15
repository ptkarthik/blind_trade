
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from app.services.intraday_engine import IntradayEngine
from app.services.liquidity_service import liquidity_service
import app.services.ta_intraday as ta_intraday

async def test_v32_logic():
    print("🧪 Starting V3.2 Logic Verification...")
    
    # Mock data for ADV20 and benchmarks
    symbol = "TEST_STOCK.NS"
    liquidity_service.liquidity_data[symbol] = {
        "adv20": 300000, # Low Liquidity
        "level": "Low",
        "last_updated": datetime.utcnow().timestamp()
    }
    
    # Mock Same-Time Benchmark (e.g. 09:30 AM)
    time_bucket = "09:30"
    liquidity_service.benchmarks[symbol] = {
        time_bucket: 10000 # 10k avg vol at 09:30
    }
    
    # 1. Create Mock DF
    times = pd.date_range("2026-03-15 09:00", periods=50, freq="5min")
    df = pd.DataFrame({
        "open": [100.0] * 50,
        "high": [101.0] * 50,
        "low": [99.0] * 50,
        "close": [100.5] * 50,
        "volume": [20000] * 50 # High RVOL (2x benchmark)
    }, index=times)
    df.attrs["symbol"] = symbol
    
    # Test RVOL Calculation in ta_intraday
    print(f"Checking {symbol} at {df.index[-1].strftime('%H:%M')}...")
    res = ta_intraday.IntradayTechnicalAnalysis.analyze_stock(df)
    
    print(f"Result RVOL: {res.get('rvol_val')}x")
    print(f"ADV20: {res.get('adv20')}")
    print(f"Liquidity Level: {res.get('liq_level')}")
    
    # Verify Eligibility in Engine
    engine = IntradayEngine()
    # Mocking analyze_stock parts to test the Hard Filter logic directly
    
    def test_eligibility(score, adv, rvol, time_str):
        now_time = datetime.strptime(time_str, "%H:%M").time()
        block_trade = False
        block_reason = None
        
        # Time Guard
        if now_time < datetime.strptime("09:25", "%H:%M").time():
            block_trade = True
            block_reason = "Opening volatility guard (pre-09:25)"
        elif adv < 200000 and rvol < 2.5:
            block_trade = True
            block_reason = "Extremely low liquidity"
        elif adv < 500000 and rvol < 2.0:
            block_trade = True
            block_reason = "Low liquidity – insufficient volume confirmation"
            
        print(f"Test -> Score: {score}, ADV: {adv}, RVOL: {rvol}, Time: {time_str}")
        if block_trade:
             print(f"   [REJECTED] {block_reason}")
        else:
             is_liquid = (adv >= 500000) or (adv < 500000 and rvol >= 2.5)
             if score >= 70 and is_liquid:
                  print(f"   [ACCEPTED] BUY")
             else:
                  print(f"   [WATCHLIST/IGNORE]")

    print("\n--- Scenarios ---")
    test_eligibility(80, 150000, 1.5, "10:00") # Extremely Low Liq -> Reject
    test_eligibility(80, 150000, 3.0, "10:00") # Extremely Low Liq, but Massive RVOL (>2.5) -> Accept
    test_eligibility(80, 350000, 1.5, "10:00") # Low Liq -> Watchlist/Reject
    test_eligibility(80, 350000, 2.6, "10:00") # Low Liq with High RVOL -> Accept BUY
    test_eligibility(85, 1000000, 1.2, "09:20") # Morning Guard -> Reject
    test_eligibility(85, 1000000, 1.2, "09:30") # Liquid Stock -> Accept BUY (even if RVOL lowish)
    
if __name__ == "__main__":
    asyncio.run(test_v32_logic())
