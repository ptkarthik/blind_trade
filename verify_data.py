import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.market_data import market_service
from app.core.config import settings

async def verify_real_data():
    print("----------------------------------------------------------------")
    print("             REAL-TIME DATA VERIFICATION REPORT                 ")
    print("----------------------------------------------------------------")
    
    symbol = "RELIANCE"
    print(f"Target Symbol: {symbol}")
    print(f"API Key Configured: {'YES' if settings.MARKET_DATA_API_KEY else 'NO'}")
    
    # Initialize Service
    await market_service.initialize()
    
    # Fetch Data
    print(f"Fetching Live Price...")
    data = await market_service.get_live_price(symbol)
    
    print("\n[RESULT]")
    print(f"Symbol: {data['symbol']}")
    print(f"Price : {data['price']}")
    print(f"Source: {data.get('source', 'UNKNOWN')}")
    
    if "TwelveData" in data.get('source', ''):
        print("\n[SUCCESS] -> Using Real-Time Twelve Data API.")
    else:
        print("\n[WARNING] -> Using Fallback Data (Yahoo/Mock). Check API Key/Credits.")

    print("\n----------------------------------------------------------------")
    print("             CHECKING MARKET STATUS API                         ")
    print("----------------------------------------------------------------")
    try:
        status = await market_service.get_market_status()
        print(f"NIFTY 50 : {status['nifty_50']}")
        print(f"INDIA VIX: {status['india_vix']}")
        print(f"Status   : {status['status']}")
        print("[SUCCESS] -> Market Status API is working.")
    except Exception as e:
        print(f"[FAILED] -> Market Status API crashed: {e}")


if __name__ == "__main__":
    asyncio.run(verify_real_data())
