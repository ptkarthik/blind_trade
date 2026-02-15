
import sqlite3
import json
import os

def check_results():
    # List of potential DB locations
    db_files = ['blind_trade.db', 'backend/blind_trade.db']
    
    print(f"CWD: {os.getcwd()}")
    
    for db_path in db_files:
        print(f"\n===== Checking DB: {db_path} =====")
        if not os.path.exists(db_path):
            print("File does not exist.")
            continue
            
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, status, type, result, error_details, created_at FROM jobs ORDER BY created_at DESC LIMIT 3")
            jobs = cursor.fetchall()
            
            if not jobs:
                print("No jobs found in this DB.")
                conn.close()
                continue

            print(f"Found {len(jobs)} recent jobs:")
            for job in jobs:
                job_id, status, job_type, result_json, error_details, created_at = job
                print(f"\n--- Job {job_id} ({created_at}) ---")
                print(f"Status: {status} | Type: {job_type}")
                
                if error_details:
                    print(f"❌ Error Details: {error_details}")

                if result_json:
                    try:
                        result = json.loads(result_json)
                        data = result.get("data", [])
                        errors = result.get("errors", [])
                        
                        print(f"Status Msg: {result.get('status_msg')}")
                        print(f"Progress: {result.get('progress')} / {result.get('total_steps')}")
                        print(f"Signals in 'data' field: {len(data)}")
                        
                        if errors:
                            print(f"ERRORS ({len(errors)}): {errors[:2]}...")
                        
                        # Print first signal if data exists
                        if data:
                             first = data[0]
                             print(f"Sample Signal: {first.get('symbol')} Type: {first.get('signal')} Score: {first.get('score')}")
                    except:
                        print("Invalid JSON in result")
                else:
                    print("Result is empty.")
            
            conn.close()
        except Exception as e:
            print(f"Error accessing {db_path}: {e}")

if __name__ == "__main__":
    check_results()
