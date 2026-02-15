import sys
import os
import asyncio

# Add current dir to path
sys.path.append(os.getcwd())

print("Attempting to import app.main...")
try:
    from app.main import app
    print("SUCCESS: app.main imported successfully.")
except Exception as e:
    print(f"FAILURE: Import failed with error: {e}")
    import traceback
    traceback.print_exc()

print("Checking signals.py syntax...")
try:
    from app.api.api_v1.endpoints import signals
    print("SUCCESS: signals.py imported successfully.")
except Exception as e:
    print(f"FAILURE: signals.py import failed: {e}")
    import traceback
    traceback.print_exc()
