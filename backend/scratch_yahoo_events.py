import requests
import json
from datetime import datetime

symbol = "TCS.NS"
url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval=1d&events=earnings"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

r = requests.get(url, headers=headers)
if r.status_code == 200:
    data = r.json()
    try:
        events = data['chart']['result'][0]['events']['earnings']
        # events is a dict of timestamp: { 'date': ts, 'earningsDate': ts }
        print("Found Earnings Events:")
        for ts, obj in events.items():
            dt = datetime.fromtimestamp(int(ts))
            date_obj = datetime.fromtimestamp(int(obj['date']))
            print(f"Timestamp: {ts} -> {dt} / {date_obj}")
    except KeyError:
        print("No earnings found in events object.")
    print(json.dumps(data.get('chart', {}).get('result', [{}])[0].get('events', {}), indent=2))
else:
    print("Failed", r.status_code)
