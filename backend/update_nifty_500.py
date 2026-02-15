import requests
import json
import csv
import io

def fetch_nifty500():
    print("Fetching Nifty 500 list from GitHub...")
    # Using a reputable repository that maintains NSE lists
    url = "https://raw.githubusercontent.com/kprohith/nse-stock-analysis/master/ind_nifty500list.csv"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        
        csv_data = response.text
        f = io.StringIO(csv_data)
        reader = csv.DictReader(f)
        
        symbols = []
        for row in reader:
            sym = row.get("Symbol")
            if sym:
                symbols.append(sym.strip())
        
        if len(symbols) < 400:
            print(f"Warning: Only fetched {len(symbols)} symbols. Might be a partial list.")
        
        print(f"Success! Fetched {len(symbols)} symbols.")
        
        with open("app/data/nifty500.json", "w") as f_out:
            json.dump(symbols, f_out, indent=4)
        print("Updated app/data/nifty500.json")
        
        return True
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return False

if __name__ == "__main__":
    fetch_nifty500()
