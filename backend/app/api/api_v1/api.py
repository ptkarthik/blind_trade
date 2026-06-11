from fastapi import APIRouter
from app.api.api_v1.endpoints import market, signals, jobs, papertrades, settings, audit, live, positions

api_router = APIRouter()
print(f"LOADING API ROUTER. Included: market, signals, jobs, settings")
print(f"Jobs Router: {jobs.router}")

api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(papertrades.router, prefix="/papertrades", tags=["papertrades"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(live.router, prefix="/live", tags=["live"])
api_router.include_router(positions.router, prefix="/positions", tags=["positions"])
print("API ROUTER LOAD COMPLETED")
