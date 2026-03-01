import asyncio
from app.services.scanner_engine import longterm_scanner_engine
import json

async def test_lt():
    symbols = ["HDFCBANK.NS", "ZOMATO.NS", "RELIANCE.NS"]
    for sym in symbols:
        print(f"\n--- Testing Long Term Engine for {sym} ---")
        try:
            res = await longterm_scanner_engine.analyze_stock(sym)
            if res:
                print(f"Final Score: {res.get('score')} / 100")
                print(f"Action: {res.get('signal')} (Override: {res.get('guardrail_intercept', False)})")
                
                advice = res.get('advisor', {})
                hp = advice.get('holding_period', {})
                print(f"Play Type: {hp.get('driver')} - {hp.get('play_type')}")
                
                stop = advice.get('stop_loss', {})
                print(f"Stop Loss: {stop.get('type')} @ {stop.get('stop_price')}")
                
                # Verify junk filter
                fund = res.get('fundamentals', {})
                is_junk = any(d.get('label') == 'JUNK FILTER' for d in fund.get('details', []))
                print(f"Junk Filter Triggered: {is_junk}")
                
                # Check TA keys
                ta = res.get('ta', {})
                print(f"50-Week SMA in TA output: {'ema_200_val' in ta}")
            else:
                print("Skipped (Data/Filter block)")
        except Exception as e:
            print(f"Crash: {e}")

if __name__ == "__main__":
    asyncio.run(test_lt())
