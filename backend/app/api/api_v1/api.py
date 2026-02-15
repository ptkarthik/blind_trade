from fastapi import APIRouter
from app.api.api_v1.endpoints import market, signals, jobs

api_router = APIRouter()
print(f"LOADING API ROUTER. Included: market, signals, jobs")
print(f"Jobs Router: {jobs.router}")

api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
print("API ROUTER LOAD COMPLETED")
