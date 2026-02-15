import os
from twelvedata import TDClient
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("MARKET_DATA_API_KEY")
td = TDClient(apikey=key)

try:
    print("Searching for RELIANCE...")
    res = td.symbol_search(symbol="RELIANCE").as_json()
    for s in res:
        print(f"  {s['symbol']} - {s['name']} ({s['exchange']}) [{s['type']}]")
except Exception as e:
    print(f"Failed: {e}")
