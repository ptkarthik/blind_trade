import asyncio
from app.services.intraday_engine import intraday_engine

async def test():
    print("Testing Intraday Engine directly...")
    result = await intraday_engine.run_scan("test-job-123")
    print("Done. Success:", len(result.get("data", [])))

if __name__ == "__main__":
    asyncio.run(test())
