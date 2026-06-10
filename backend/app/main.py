from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.market_data import market_service

import os
# PROXY BYPASS (Fix for N/A values and Connectivity issues)
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
import socket
# Phase 97: Global socket timeout to prevent hanging threads from network data
socket.setdefaulttimeout(15.0)

import sys
import io
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: __file__: {__file__}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    # 1. Initialize Market Service
    await market_service.initialize()
    
    # 2. Ensure Database Tables exist
    from app.db.session import engine
    from app.models.job import Base
    # Import all models to ensure they are registered with Base.metadata
    from app.models.job import Job
    from app.models.papertrade import PaperTrade, Account
    from app.models.swing_trade import SwingTrade
    from app.models.scan_snapshot import ScanSnapshot
    from app.models.trap_pattern import TrapPattern
    
    async with engine.begin() as conn:
        # This will create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
    
    # 3. Synchronize TradeManager from DB
    from app.services.trade_manager import trade_manager
    await trade_manager.sync_from_db()
    
    # Sync Portfolio Engine state with active trades
    from app.services.portfolio_engine import portfolio_engine
    portfolio_engine.sync_active_positions(trade_manager.active_trades)
    
    # 4. Cleanup disabled in API tier
    # Background Runner is now handled by external Worker process (app.worker.worker_main)
    # The worker has its own Zombie Job Reaper, so the API should not touch job states on reload.
            
    # Background Runner is now handled by external Worker process (app.worker.worker_main)
    print("API Startup Complete. Background Jobs System Ready.")

from fastapi.staticfiles import StaticFiles
import os

# Set all CORS enabled origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression for large JSON payloads (Fast Toggles)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Mount Reports for Visualization
if not os.path.exists("app/reports"):
    os.makedirs("app/reports")
app.mount("/reports", StaticFiles(directory="app/reports"), name="reports")

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Blind Trade API is running", "status": "OK"}
