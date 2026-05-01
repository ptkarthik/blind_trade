import asyncio
from app.services.ta_swing import ta_swing
from app.services.market_data import market_service
import yfinance as yf

async def test_swing():
    syms = ["ECLERX.NS", "RACLGEAR.NS", "JNKINDIA.NS", "PGHH.NS", "CUPID.NS", "ADVANCE.NS"]
    for sym in syms:
        print(f"Testing {sym}")
        df = yf.Ticker(sym).history(period="1y", interval="1d")
        if df.empty:
            print("No data")
            continue
        df.columns = [c.lower() for c in df.columns]
        
        ctx = ta_swing.compute_context(df)
        pb = ta_swing.analyze_pullback(df, nifty_20d_ret=6.2, ctx=ctx)
        bo = ta_swing.analyze_breakout(df, nifty_20d_ret=6.2, ctx=ctx)
        
        print(f"  PB: {pb.get('reason', 'MATCH')}")
        print(f"  BO: {bo.get('reason', 'MATCH')}")
        print()

if __name__ == "__main__":
    asyncio.run(test_swing())
