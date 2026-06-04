import sqlite3, json

conn = sqlite3.connect('backend/blind_trade.db')
cur = conn.cursor()
cur.execute('SELECT result, status FROM jobs WHERE type="intraday" ORDER BY updated_at DESC LIMIT 1')
row = cur.fetchone()

if row:
    result_str, status = row
    print("STATUS:", status)
    result = json.loads(result_str) if result_str else {}
    print("PROGRESS:", result.get("progress"))
    print("STATUS_MSG:", result.get("status_msg"))
    print("TOTAL DATA ITEMS:", len(result.get("data", [])))
else:
    print("No jobs found")
