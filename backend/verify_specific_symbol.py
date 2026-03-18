
import asyncio
import httpx

async def verify():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Trigger full intraday scan
        print("Triggering full intraday scan...")
        payload = {"type": "intraday"}
        res = await client.post("http://127.0.0.1:8012/api/v1/jobs/scan", json=payload)
        print(f"Status: {res.status_code}")
        print(f"Result: {res.json()}")

if __name__ == "__main__":
    asyncio.run(verify())
