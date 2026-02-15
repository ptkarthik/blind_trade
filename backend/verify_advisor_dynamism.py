
import requests
import time
import json

BASE_URL = "http://localhost:8002/api/v1"

def test_advisor_fields():
    print("Triggering new scan...")
    # Trigger a sector scan (faster)
    try:
        trigger_res = requests.post(f"{BASE_URL}/jobs/scan", json={"type": "sector_scan"})
        job_id = trigger_res.json().get("id")
        print(f"Job ID: {job_id}")
    except:
        print("Failed to trigger job. Is the backend running on 8002?")
        return

    print("Waiting for job completion...")
    for _ in range(60): # 2 mins max
        res = requests.get(f"{BASE_URL}/signals/sectors")
        data = res.json()
        
        # Check if we have signals
        all_signals = []
        for sector, details in data.items():
            if isinstance(details, dict) and "signals" in details:
                all_signals.extend(details["signals"])
        
        if all_signals:
            print(f"Found {len(all_signals)} signals!")
            # Inspect first signal
            s = all_signals[0]
            adv = s.get("investment_advisory") or s.get("advisor")
            
            if adv:
                print("✅ Found Advisor Data!")
                print(f"Holding Period: {adv.get('holding_period', {}).get('period_display')}")
                print(f"3Y Target: {adv.get('targets', {}).get('3_year_target')}")
                print(f"Stop Loss: {adv.get('stop_loss', {}).get('stop_price')}")
                print(f"Scenarios: {len(adv.get('scenarios', []))} found")
                
                # Check specifics
                if adv.get('scenarios'):
                    print(f"First Scenario: {adv['scenarios'][0]}")
                
                print("\nFull Advisor JSON excerpt:")
                print(json.dumps(adv, indent=2))
                return True
            else:
                print("❌ Advisor Data missing in signal.")
        
        time.sleep(2)
    
    print("Timeout or no signals found.")
    return False

if __name__ == "__main__":
    test_advisor_fields()
