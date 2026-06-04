import sqlite3, json
conn = sqlite3.connect('backend/blind_trade.db')
cur = conn.cursor()
cur.execute('SELECT id, status, result, created_at, updated_at FROM jobs WHERE type="intraday" ORDER BY created_at DESC LIMIT 5')
for row in cur.fetchall():
    print(f"ID: {row[0]}")
    print(f"STATUS: {row[1]}")
    print(f"CREATED: {row[3]}")
    print(f"UPDATED: {row[4]}")
    result_str = row[2]
    if result_str:
        result = json.loads(result_str)
        print(f"PROGRESS: {result.get('progress')}")
        print(f"MSG: {result.get('status_msg')}")
        print(f"TOTAL: {result.get('total')}")
    else:
        print("RESULT: None")
    print("-" * 40)
