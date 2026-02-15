import asyncio
from app.services.market_data import market_service
from app.services.ta import ta_engine

async def verify_system_state():
    print("--- Starting System Verification ---")
    
    # 1. Initialize Market Service (Simulate Startup)
    print("Initializing Market Service...")
    await market_service.initialize()
    
    total_stocks = len(market_service.stock_master)
    print(f"Total Stocks Loaded: {total_stocks}")
    
    # 2. Check Sector Distribution
    sectors = ["Banking", "IT", "Auto", "Pharma", "Energy", "FMCG", "Metal"]
    print("\n--- Sector Distribution ---")
    for sec in sectors:
        stocks = market_service.get_stocks_by_sector(sec)
        print(f"{sec}: {len(stocks)} stocks")
        if len(stocks) > 0:
            print(f"  Sample: {stocks[:3]}")
    
    # 3. Test Analysis on a Benchmark Stock
    print("\n--- Test Analysis (RELIANCE) ---")
    df = await market_service.get_ohlc("RELIANCE", period="5d", interval="15m")
    print(f"RELIANCE Data Shape: {df.shape}")
    
    if not df.empty:
        analysis = ta_engine.analyze_stock(df, mode="intraday")
        print(f"Analysis Result: score={analysis.get('score')}, signal={analysis.get('trend')}")
    
    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(verify_system_state())
