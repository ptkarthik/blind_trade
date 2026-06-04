import asyncio
import os
import sys

# Add backend dir to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.swing_engine import swing_engine

async def main():
    # Initialize some required context if needed
    await swing_engine.refresh_market_context()
    
    print("Testing ADVAIT.NS...")
    result = await swing_engine.analyze_stock("ADVAIT.NS")
    if result:
        print(f"Score: {result.get('score')}")
        print(f"Reasons: {result.get('reasons')}")
    else:
        print("No match or rejected.")

if __name__ == "__main__":
    asyncio.run(main())
