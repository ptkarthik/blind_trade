
import yfinance as yf
import pandas as pd
import json

def debug_data(symbol="SBIN.NS"):
    print(f"Fetching data for {symbol}...")
    ticker = yf.Ticker(symbol)
    
    print("\n--- CASH FLOW (for FCF) ---")
    try:
        # Annual Cashflow
        cf = ticker.cashflow
        if not cf.empty:
            print(cf.head(10))
            # Check for Free Cash Flow keys
            # Often 'Free Cash Flow', 'Operating Cash Flow', 'Capital Expenditure'
        else:
            print("No Cashflow Data Found")
    except Exception as e:
        print(f"Error fetching cashflow: {e}")

    print("\n--- BALANCE SHEET (for Piotroski) ---")
    try:
        bs = ticker.balance_sheet
        if not bs.empty:
            print(bs.head(5))
        else:
            print("No Balance Sheet Found")
    except: pass
    
    print("\n--- HOLDING INFO (for Promoter Change) ---")
    try:
        # Major Holders
        print("Major Holders:")
        print(ticker.major_holders)
        print("Institutional Holders:")
        print(ticker.institutional_holders)
        print("Insider Transactions (Change?):")
        # Insider transactions might show recent buying/selling
        print(ticker.insider_transactions) 
    except Exception as e:
        print(f"Error fetching holders: {e}")

    print("\n--- INFO DICT KEYS (Quick Check) ---")
    info = ticker.info
    interesting_keys = [k for k in info.keys() if any(x in k.lower() for x in ['cash', 'flow', 'debt', 'beta', 'held', 'margin'])]
    print(json.dumps({k: info.get(k) for k in interesting_keys}, indent=2))

if __name__ == "__main__":
    debug_data()
