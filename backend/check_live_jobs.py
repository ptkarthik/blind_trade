import sqlite3
import json

def check_live_jobs():
    conn = sqlite3.connect('blind_trade.db')
    c = conn.cursor()
    
    print("\n--- Live Jobs Status ---")
    c.execute("SELECT id, type, status, updated_at, result FROM jobs WHERE status IN ('processing', 'pending') ORDER BY updated_at DESC")
    rows = c.fetchall()
    
    c.execute("SELECT id, type, status, updated_at, result FROM jobs ORDER BY updated_at DESC LIMIT 10")
    rows = c.fetchall()
    print("\n--- Last 10 Jobs (All Statuses) ---")
    for r in rows:
        res_size = len(r[4]) if r[4] else 0
        print(f"ID: {r[0]} | Type: {repr(r[1])} | Status: {repr(r[2])} | Size: {res_size}")

    for row in rows:
        job_id, job_type, status, updated, result_json = row
        print(f"\nID: {job_id}")
        print(f"Type: {job_type}")
        print(f"Status: {status}")
        print(f"Updated: {updated}")
        
        if result_json:
            try:
                result = json.loads(result_json)
                print(f"Progress: {result.get('progress')} / {result.get('total_steps')}")
                print(f"Status Msg: {result.get('status_msg')}")
                data = result.get('data', [])
                print(f"Data Records Found: {len(data)}")
                if data:
                    print("First Result Sample:", {k: data[0][k] for k in ['symbol', 'signal', 'score', 'signal_type'] if k in data[0]})
                
                failed = result.get('failed_symbols', [])
                print(f"Failed Symbols: {len(failed)}")
            except Exception as e:
                print(f"Error parsing result JSON: {e}")
        else:
            print("Result field is EMPTY.")

check_live_jobs()
