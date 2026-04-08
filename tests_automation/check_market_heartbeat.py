
import asyncio
import os
import sys

# Trace Path to find backend/app
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.market_data import market_service

async def check_pulse():
    print("--- 🛰️ Checking Market Heartbeat (RELIANCE) ---")
    try:
        price = await market_service.get_latest_price("RELIANCE.NS")
        if price and "price" in price:
            print(f"✅ Pulse OK: {price['symbol']} = {price['price']}")
        else:
            print(f"❌ Pulse Failed: {price}")
    except Exception as e:
        print(f"🚨 Heartbeat Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_pulse())
