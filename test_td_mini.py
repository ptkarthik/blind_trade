from twelvedata import TDClient
import os
from dotenv import load_dotenv

load_dotenv("backend/.env")
api_key = os.getenv("MARKET_DATA_API_KEY")

def test_td():
    print(f"Using API Key: {api_key[:5]}...")
    td = TDClient(apikey=api_key)
    
    symbols = ["RELIANCE:NSE", "ZOMATO:NSE"]
    
    for symbol in symbols:
        print(f"\n--- Testing {symbol} ---")
        try:
            # 1. Price
            price_res = td.price(symbol=symbol).as_json()
            print(f"Price Response: {price_res}")
            
            # 2. Time Series
            ts_res = td.time_series(symbol=symbol, interval="1day", outputsize=5).as_json()
            if "values" in ts_res:
                print(f"TS Found: {ts_res['values'][0]}")
            else:
                print(f"TS Error: {ts_res}")
        except Exception as e:
            print(f"TD Error for {symbol}: {e}")

if __name__ == "__main__":
    test_td()
