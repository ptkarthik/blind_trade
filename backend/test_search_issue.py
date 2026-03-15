
import asyncio
import httpx

async def test_search():
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. Test Suggesions
        print("Testing Suggestions for 'ZOMATO'...")
        res = await client.get("http://localhost:8012/api/v1/market/search?q=ZOMATO")
        print(f"Suggestions Status: {res.status_code}")
        print(f"Suggestions: {res.json()}")
        
        # 2. Test Analyze (Intraday)
        print("\nTesting Analyze for 'ZOMATO' (Intraday)...")
        res = await client.get("http://localhost:8012/api/v1/signals/ZOMATO?mode=intraday")
        print(f"Analyze Status: {res.status_code}")
        if res.status_code == 200:
            print(f"Analyze Result Keys: {res.json().keys()}")
        else:
            print(f"Analyze Error: {res.text}")

if __name__ == "__main__":
    asyncio.run(test_search())
