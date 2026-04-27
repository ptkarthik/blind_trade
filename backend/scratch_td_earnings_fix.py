import requests
import json

api_key = "d010d8a55c2f42a6afb46765da226871" # Assuming we can pull it or test it. Wait, I shouldn't hardcode if I don't know it. 
# I will dynamic load it.
import os
import sys

# Load env variables since app.core.config might be tricky to import without side effects.
# Wait, I will just import settings.
sys.path.append(r"c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend")
from app.core.config import settings

api_key = settings.MARKET_DATA_API_KEY
url = f"https://api.twelvedata.com/earnings?symbol=RELIANCE,TCS&apikey={api_key}"

try:
    r = requests.get(url, timeout=5)
    print("Status:", r.status_code)
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(e)
