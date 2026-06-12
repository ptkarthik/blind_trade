import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import delete
from app.models.user import User

async def clear():
    async with AsyncSessionLocal() as db:
        await db.execute(delete(User))
        await db.commit()

asyncio.run(clear())
