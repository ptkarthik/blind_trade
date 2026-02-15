
import sys
import os

# Add backend dir to path
sys.path.append(os.getcwd())

from app.main import app

print("--- REGISTERED ROUTES ---")
for route in app.routes:
    if hasattr(route, "path"):
        print(f"{route.methods} {route.path}")
    else:
        print(route)
print("-------------------------")
