
import sqlite3
import json
from datetime import datetime, timedelta

def check_times():
    db_path = 'backend/blind_trade.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print(f"--- Checking Job Timestamps in {db_path} ---")
    cursor.execute("SELECT id, created_at, updated_at, status FROM jobs ORDER BY created_at DESC LIMIT 5")
    jobs = cursor.fetchall()
    
    for job in jobs:
        j_id, created, updated, status = job
        print(f"\nJob ID: {j_id}")
        print(f"Status: {status}")
        print(f"UTC Created: {created}")
        print(f"UTC Updated: {updated}")
        
        # Simulating API conversion
        try:
            # SQLite stores as strings, need to parse
            # Format usually: 2026-02-08 17:30:39.549359
            fmt = "%Y-%m-%d %H:%M:%S.%f"
            upd_dt = datetime.strptime(updated, fmt)
            ist_dt = upd_dt + timedelta(hours=5, minutes=30)
            print(f"CALC IST (Kolkata): {ist_dt.strftime('%d %b, %H:%M:%S')}")
        except Exception as e:
            print(f"Error parsing/calculating: {e}")
            
    conn.close()

if __name__ == "__main__":
    check_times()
