import asyncio
from app.services.kite_data import kite_data

async def check():
    await kite_data.initialize()
    status = kite_data.get_status()
    print("STATUS:", status)
    if status.get("is_ready"):
        print("Checking live data (NIFTY 50 LTP)...")
        ltp = await kite_data.get_ltp("NSE:NIFTY 50")
        print("LTP:", ltp)
        if ltp and ltp > 0:
            print("✅ Kite is fully connected and returning live market data!")
        else:
            print("❌ Kite is connected but failed to return LTP.")
    else:
        print("❌ Kite is NOT connected.")

if __name__ == "__main__":
    asyncio.run(check())
