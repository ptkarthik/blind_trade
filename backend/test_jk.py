import asyncio
from app.services.delivery_service import delivery_service

async def run():
    print(await delivery_service.get_delivery_pct('J&KBANK.NS'))

asyncio.run(run())
