import asyncio
from app.services.kite_data import kite_data

async def test_login():
    print("Initializing Kite Data...")
    await kite_data.initialize()
    status = kite_data.get_status()
    print(f"Status: {status}")

if __name__ == "__main__":
    asyncio.run(test_login())
