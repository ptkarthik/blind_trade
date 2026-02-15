
import sys
import asyncio

print("--- Checking App Startup ---")
try:
    from app.core.config import settings
    print(f"Config Loaded. Project: {settings.PROJECT_NAME}")
    
    from app.db.session import engine
    print("Database Engine Initialized.")
    
    # Try importing main API router
    from app.api.api_v1.api import api_router
    print("API Router Imported.")
    
    print("✅ App Integrity Check PASSED.")
except Exception as e:
    print(f"❌ App Integrity Check FAILED: {e}")
    import traceback
    traceback.print_exc()
