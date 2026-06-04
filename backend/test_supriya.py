import asyncio
from app.services.intraday_engine import intraday_engine

async def test_supriya():
    print("Analyzing SUPRIYA.NS...")
    result = await intraday_engine.analyze_stock("SUPRIYA.NS")
    print(result)

if __name__ == "__main__":
    asyncio.run(test_supriya())
