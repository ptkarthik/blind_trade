import asyncio
from app.services.kite_data import kite_data

async def main():
    try:
        print("Acquiring lock in new loop...")
        async with kite_data._init_lock:
            print("Acquired!")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    # Simulate uvicorn starting a new loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
