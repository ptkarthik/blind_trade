import asyncio
from app.services.kite_data import kite_data

async def test_login():
    success = await kite_data._auto_login()
    print(f"Auto-login success: {success}")

if __name__ == "__main__":
    asyncio.run(test_login())
