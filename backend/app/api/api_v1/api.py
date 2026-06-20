from fastapi import APIRouter, Depends
from app.api.api_v1.endpoints import market, signals, jobs, papertrades, settings, audit, live, positions, auth, logs, broker
from app.api.deps import get_current_user

api_router = APIRouter()
print(f"LOADING API ROUTER. Included: market, signals, jobs, settings, auth, broker")

# Auth router does NOT require the token lock (so users can login)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# All other routers REQUIRE the token lock
locked = [Depends(get_current_user)]

api_router.include_router(market.router, prefix="/market", tags=["market"], dependencies=locked)
api_router.include_router(signals.router, prefix="/signals", tags=["signals"], dependencies=locked)
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"], dependencies=locked)
api_router.include_router(papertrades.router, prefix="/papertrades", tags=["papertrades"], dependencies=locked)
api_router.include_router(settings.router, prefix="/settings", tags=["settings"], dependencies=locked)
api_router.include_router(audit.router, prefix="/audit", tags=["audit"], dependencies=locked)
api_router.include_router(live.router, prefix="/live", tags=["live"], dependencies=locked)
api_router.include_router(positions.router, prefix="/positions", tags=["positions"], dependencies=locked)
api_router.include_router(logs.router, prefix="/system/logs", tags=["system"], dependencies=locked)
api_router.include_router(broker.router, prefix="/broker", tags=["broker"], dependencies=locked)
print("API ROUTER LOAD COMPLETED")
