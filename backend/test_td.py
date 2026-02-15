import os
from twelvedata import TDClient
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("MARKET_DATA_API_KEY")
print(f"Using Key: {key[:5]}...")

td = TDClient(apikey=key)

try:
    print("Testing Price Fetch for RELIANCE:NSE...")
    price = td.price(symbol="RELIANCE:NSE").as_json()
    print(f"Success! Price: {price['price']}")
    
    print("Testing Time Series (15min) for TCS:NSE...")
    ts = td.time_series(symbol="TCS:NSE", interval="15min", outputsize=5).as_json()
    print(f"Success! First 5 candles retrieved.")
    for candle in ts:
        print(f"  {candle['datetime']}: {candle['close']}")
except Exception as e:
    print(f"Failed: {e}")
