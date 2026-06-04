import asyncio
import logging
from app.services.kite_data import kite_data

logging.basicConfig(level=logging.INFO)

async def test_login():
    print("Testing Kite initialization and auto-login...")
    await kite_data.initialize()
    status = kite_data.get_status()
    print("STATUS:", status)

if __name__ == "__main__":
    asyncio.run(test_login())
