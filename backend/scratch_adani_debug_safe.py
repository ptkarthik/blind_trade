import asyncio
import sys
import logging
from pprint import pprint
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def run_analysis():
    print("--- ADANIGREEN INTRADAY ANALYSIS ---")
    symbol = "ADANIGREEN.NS"
    
    # 2. Fetch Data Manually using yfinance to avoid any app-level hanging
    print("\n2. Fetching Market Data...")
    try:
        t = yf.Ticker(symbol)
        df_15m = t.history(period="5d", interval="15m")
        df_1d = t.history(period="1mo", interval="1d")
        
        if df_15m.empty or df_1d.empty:
            print("❌ Failed to fetch data.")
            return
            
        df_15m.columns = [c.lower() for c in df_15m.columns]
        df_1d.columns = [c.lower() for c in df_1d.columns]
        
        live_price = float(df_15m['close'].iloc[-1])
        open_price = float(df_1d['open'].iloc[-1])
        change_pct = round(((live_price - open_price) / open_price) * 100, 2)
        
        live_data = {
            "symbol": symbol,
            "price": live_price,
            "change_percent": change_pct
        }
            
        print(f"✅ Data fetched. 15m rows: {len(df_15m)}, 1d rows: {len(df_1d)}")
        print(f"   Current Price: {live_price}")
        print(f"   Day Change: {change_pct}%")
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    # 3. Run Engine Analysis
    print("\n3. Running Intraday Engine Analysis...")
    try:
        from app.services.intraday_engine import intraday_engine
        # The engine expects the app context, but intraday_engine is a pure function essentially
        result = await intraday_engine.analyze_stock(symbol, live_data, df_15m, df_1d)
        
        print("\n=== ENGINE RESULT ===")
        print(f"Action: {result.get('action')}")
        print(f"Score:  {result.get('score')}")
        if result.get('target'):
            print(f"Target: {result.get('target')} | SL: {result.get('stop_loss')}")
        
        print("\nReasons/Penalties:")
        for reason in result.get('reasons', []):
            impact = reason.get('impact_score', 0)
            prefix = "🟢" if impact >= 0 else "🔴"
            print(f"{prefix} [{impact:3d}] {reason.get('message')}")
            
    except Exception as e:
        print(f"Error in engine analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_analysis())
