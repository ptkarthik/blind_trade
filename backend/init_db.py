
import asyncio
from app.db.session import engine
from app.models.job import Job

async def init_models():
    async with engine.begin() as conn:
        print("Creating tables...")
        await conn.run_sync(Job.metadata.create_all)
        print("Tables created.")

if __name__ == "__main__":
    asyncio.run(init_models())
