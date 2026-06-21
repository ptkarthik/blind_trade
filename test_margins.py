import asyncio
import os
import sys

# Add backend dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from app.db.session import SessionLocal
from app.services.kite_data import kite_data

async def main():
    print("Connecting to Kite DB...")
    db = SessionLocal()
    await kite_data._ensure_session_loop()
    print("Kite ready?", kite_data.is_ready)
    
    try:
        margins = await kite_data.get_margins()
        print("MARGINS:", margins)
    except Exception as e:
        print("ERROR:", str(e))

if __name__ == "__main__":
    asyncio.run(main())
