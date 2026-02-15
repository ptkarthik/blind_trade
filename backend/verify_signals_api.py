
import requests
import json
from datetime import datetime

API_URL = "http://localhost:8002/api/v1/signals/sectors"

def verify_signals():
    print(f"--- Verifying Signals API: {API_URL} ---")
    try:
        response = requests.get(API_URL)
        if response.status_code != 200:
            print(f"❌ API Error: {response.status_code}")
            return

        data = response.json()
        print("✅ API Response Received.")
        
        total_signals = 0
        timestamp = "Unknown"
        
        sectors = ["Banking", "IT", "Energy", "Pharma", "FMCG"]
        
        for sector, details in data.items():
            buys = len(details.get("buys", []))
            sells = len(details.get("sells", []))
            holds = len(details.get("holds", []))
            count = buys + sells + holds
            total_signals += count
            
            ts = details.get("last_updated")
            if ts and timestamp == "Unknown":
                timestamp = ts
                
            if count > 0:
                print(f"   {sector}: {count} signals (Updated: {ts})")
        
        print(f"\n--- SUMMARY ---")
        print(f"Total Signals Found: {total_signals}")
        print(f"Last Updated Timestamp: {timestamp}")
        
        if total_signals > 0:
            print("✅ SUCCESS: Signals are being returned!")
        else:
            print("❌ FAILURE: No signals found in API response.")

    except Exception as e:
        print(f"❌ Connection Error: {e}")

if __name__ == "__main__":
    verify_signals()
