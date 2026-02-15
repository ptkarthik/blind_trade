
import requests
import time
import sys

BASE_URL = "http://localhost:8001/api/v1"
BASE_URL_FALLBACK = "http://localhost:8000/api/v1"

def test_trigger():
    # Use explicit variable instead of global reassignment to avoid syntax issues
    current_base_url = BASE_URL
    
    print("--- Testing Scan Trigger ---")
    
    # 1. Trigger Scan
    print("POST /jobs/scan")
    try:
        res = requests.post(f"{current_base_url}/jobs/scan", json={"type": "full_scan"})
    except requests.exceptions.ConnectionError:
        print(f"⚠️ Port 8001 failed. Trying 8000...")
        current_base_url = BASE_URL_FALLBACK
        try:
            res = requests.post(f"{current_base_url}/jobs/scan", json={"type": "full_scan"})
        except requests.exceptions.ConnectionError:
            print("❌ Both Port 8001 and 8000 failed. API is DOWN.")
            return

    if res.status_code != 200:
        print(f"❌ Failed to trigger scan: {res.text}")
        return
    
    job = res.json()
    job_id = job['id']
    print(f"✅ Job Created: {job_id} (Status: {job['status']}) on {current_base_url}")
    
    # 2. Poll Status
    print("Polling Status...")
    for i in range(5):
        time.sleep(1)
        res = requests.get(f"{current_base_url}/jobs/status")
        status_data = res.json()
        
        # Check if our job is the latest
        if status_data['id'] == job_id:
            print(f"[{i+1}s] Status: {status_data['status']}")
            if status_data['status'] == 'processing':
                print("✅ Job moved to PROCESSING! Background task is working.")
                
                # Stop it to not waste resources
                requests.post(f"{current_base_url}/jobs/stop")
                return
        else:
            print(f"[{i+1}s] Latest Job ID mismatch: {status_data['id']}")
    
    print("❌ Job did not move to PROCESSING in 5 seconds.")

if __name__ == "__main__":
    test_trigger()
