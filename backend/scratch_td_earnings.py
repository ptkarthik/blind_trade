from app.core.config import settings
import requests
import json

api_key = settings.MARKET_DATA_API_KEY
url = f"https://api.twelvedata.com/earnings?symbol=RELIANCE,TCS&apikey={api_key}"

r = requests.get(url)
print(r.status_code)
print(json.dumps(r.json(), indent=2))
