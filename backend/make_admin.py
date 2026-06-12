import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import update
from app.models.user import User

async def make_admin():
    async with AsyncSessionLocal() as db:
        await db.execute(update(User).values(is_admin=True))
        await db.commit()
        print('All users are now admins!')

asyncio.run(make_admin())
