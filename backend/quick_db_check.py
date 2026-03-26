import sqlite3
import json

def quick_check():
    conn = sqlite3.connect('blind_trade.db')
    c = conn.cursor()
    c.execute("SELECT id, type, status, result FROM jobs ORDER BY updated_at DESC LIMIT 10")
    rows = c.fetchall()
    for r in rows:
        job_id, job_type, status, res_json = r
        try:
            res = json.loads(res_json) if res_json else {}
            data = res.get('data', [])
            progress = res.get('progress', 0)
            total = res.get('total_steps', 0)
            print(f"ID: {job_id[:8]} | Type: {job_type:<10} | Status: {status:<12} | Data: {len(data):<5} | Progress: {progress}/{total}")
        except:
            print(f"ID: {job_id[:8]} | Error parsing JSON for {job_id}")
    conn.close()

quick_check()
