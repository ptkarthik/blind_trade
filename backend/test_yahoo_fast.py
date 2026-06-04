import asyncio
from app.services.yahoo_fast import yahoo_fast

async def test():
    print("Testing YahooFast...")
    res = await yahoo_fast.fetch_batch(['RELIANCE.NS'])
    print(res)

if __name__ == "__main__":
    asyncio.run(test())
