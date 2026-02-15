from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.api_v1.api import api_router
from app.services.market_data import market_service

import os
# PROXY BYPASS (Fix for N/A values and Connectivity issues)
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''

import sys
print(f"DEBUG: sys.path: {sys.path}")
print(f"DEBUG: __file__: {__file__}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)


@app.on_event("startup")
async def startup_event():
    await market_service.initialize()
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

# Mount Reports for Visualization
if not os.path.exists("app/reports"):
    os.makedirs("app/reports")
app.mount("/reports", StaticFiles(directory="app/reports"), name="reports")

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
def root():
    return {"message": "Blind Trade API is running", "status": "OK"}
