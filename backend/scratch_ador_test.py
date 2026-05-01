import asyncio
import sys
import os

sys.path.append(os.getcwd())
from app.services.intraday_engine import intraday_engine

async def main():
    print("Testing ADOR.NS intraday logic...")
    res = await intraday_engine.analyze_stock("ADOR.NS")
    
    print("\n--- ANALYSIS RESULT ---")
    print(res)

if __name__ == "__main__":
    asyncio.run(main())
