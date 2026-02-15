import os
from twelvedata import TDClient
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("MARKET_DATA_API_KEY")
td = TDClient(apikey=key)

try:
    print("Testing Price Fetch for AAPL...")
    price = td.price(symbol="AAPL").as_json()
    print(f"Success! Price: {price['price']}")
except Exception as e:
    print(f"Failed: {e}")
