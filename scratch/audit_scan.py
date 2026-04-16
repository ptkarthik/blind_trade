import sqlite3
import json
from datetime import datetime

def check_data():
    conn = sqlite3.connect('backend/blind_trade.db')
    cursor = conn.cursor()
    cursor.execute("SELECT result, created_at FROM jobs WHERE type='intraday' ORDER BY created_at DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        print("No jobs found.")
        return
    
    res = json.loads(row[0])
    job_time = row[1]
    data = res.get('data', [])
    
    print(f"--- Job Created At: {job_time} ---")
    print(f"Total Signals: {len(data)}")
    
    # Top 3 signals
    top = sorted(data, key=lambda x: x.get('score', 0), reverse=True)[:5]
    for s in top:
        print(f"Symbol: {s['symbol']} | Score: {s['score']} | Signal: {s['signal']}")
        # Check if we have reasons for the score
        for group, detail in s.get('groups', {}).items():
            print(f"  {group}: {detail['score']}")
            for d in detail.get('details', []):
                print(f"     - {d}")

if __name__ == "__main__":
    check_data()
