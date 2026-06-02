import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

async def test_login():
    from app.services.kite_data import kite_data
    
    print("Initializing Kite (this calls _auto_login internally)...")
    await kite_data.initialize()
    print(f"Kite Ready: {kite_data.is_ready}")

if __name__ == "__main__":
    asyncio.run(test_login())
