
import asyncio
from app.services.market_data import market_service
from app.services.proxy_manager import proxy_manager

async def verify():
    print("Verifying Market Service with Proxy Integration...")
    
    # 1. Check Proxy Manager Init
    print("Refreshing proxies first...")
    await proxy_manager._refresh_proxies()
    if not proxy_manager.proxies:
        print("⚠️ No proxies found, but continuing to test main path.")
    else:
        print(f"✅ Proxies active: {len(proxy_manager.proxies)}")

    # 2. Test Get Live Price (Main Path)
    print("\nTesting get_live_price ('RELIANCE')...")
    data = await market_service.get_live_price("RELIANCE")
    print(f"Result: {data.get('price')} from {data.get('source')}")
    
    # 3. Test Get OHLC (Main Path)
    print("\nTesting get_ohlc ('TCS')...")
    df = await market_service.get_ohlc("TCS", period="5d", interval="15m")
    print(f"Result Check: {len(df)} rows")

if __name__ == "__main__":
    asyncio.run(verify())
