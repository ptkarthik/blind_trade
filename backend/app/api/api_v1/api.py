from fastapi import APIRouter
from app.api.api_v1.endpoints import jobs, papertrade, swing, scanner, settings, websocket, backtester, realtime, dashboard, auth, sync, market, audit, live

api_router = APIRouter()

api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(papertrade.router, prefix="/papertrade", tags=["papertrade"])
api_router.include_router(swing.router, prefix="/swing", tags=["swing"])
api_router.include_router(scanner.router, prefix="/scanner", tags=["scanner"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(websocket.router, prefix="/ws", tags=["websocket"])
api_router.include_router(backtester.router, prefix="/backtester", tags=["backtester"])
api_router.include_router(realtime.router, prefix="/realtime", tags=["realtime"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(sync.router, prefix="/sync", tags=["sync"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(live.router, prefix="/live", tags=["live"])
print("API ROUTER LOAD COMPLETED")
