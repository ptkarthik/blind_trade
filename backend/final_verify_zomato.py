
import asyncio
import sys
import os

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.market_data import market_service
from app.services.scanner_engine import scanner_engine

async def verify():
    symbol = "ZOMATO.NS"
    print(f"--- FINAL VERIFY: {symbol} ---")
    
    # 1. Live Price
    price_data = await market_service.get_live_price(symbol)
    print(f"Live Price Data: {price_data}")
    
    # 2. OHLC check
    df = await market_service.get_ohlc(symbol, period="1mo", interval="1d")
    print(f"OHLC Rows: {len(df)}")
    
    # 3. Full Analysis
    analysis = await scanner_engine.analyze_stock(symbol)
    if analysis:
        print(f"✅ Analysis Success!")
        print(f"   Score: {analysis['score']}")
        print(f"   Price: {analysis['price']}")
        print(f"   Signal: {analysis['signal']}")
    else:
        print(f"❌ Analysis Failed (Returned None)")

if __name__ == "__main__":
    asyncio.run(verify())
