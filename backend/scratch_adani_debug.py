import asyncio
import sys
import logging
from pprint import pprint

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format='%(message)s')

async def run_analysis():
    print("--- ADANIGREEN INTRADAY ANALYSIS ---")
    
    # Import services
    from app.services.market_data import market_service
    from app.services.intraday_engine import intraday_engine
    from app.services.market_discovery import market_discovery
    
    symbol = "ADANIGREEN.NS"
    
    # 1. Check if it's in the universe
    print("\n1. Universe Check:")
    universe_list = await market_discovery.get_full_market_list()
    universe = [s['symbol'] for s in universe_list]
    if symbol in universe:
        print(f"✅ {symbol} is in the scanning universe.")
    else:
        print(f"❌ {symbol} is NOT in the scanning universe!")
        
    # 2. Fetch Data
    print("\n2. Fetching Market Data...")
    try:
        live_data = await market_service.get_live_price(symbol)
        df_15m = await market_service.get_ohlc(symbol, period="5d", interval="15m")
        df_1d = await market_service.get_ohlc(symbol, period="1mo", interval="1d")
        
        if df_15m is None or df_15m.empty:
            print("❌ Failed to fetch 15m OHLC data.")
            return
        if df_1d is None or df_1d.empty:
            print("❌ Failed to fetch 1d OHLC data.")
            return
            
        print(f"✅ Data fetched. 15m rows: {len(df_15m)}, 1d rows: {len(df_1d)}")
        print(f"   Current Price: {live_data.get('price')} / {live_data.get('close')}")
        print(f"   Day Change: {live_data.get('change_percent')}%")
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    # 3. Run Engine Analysis
    print("\n3. Running Intraday Engine Analysis...")
    try:
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

if __name__ == "__main__":
    asyncio.run(run_analysis())
