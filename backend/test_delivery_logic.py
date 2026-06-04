import asyncio
from app.services.delivery_service import delivery_service

async def run():
    print("Testing get_delivery_pct...")
    res = await delivery_service.get_delivery_pct("RELIANCE.NS")
    print("Result for RELIANCE:", res)
    print("Last Used Date:", getattr(delivery_service, 'last_used_date', 'None'))

asyncio.run(run())
