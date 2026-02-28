import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), 'blind_trade.db')
if not os.path.exists(db_path):
    print("DB not found at", db_path)
else:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, type, status, created_at, error_details FROM jobs WHERE type LIKE '%swing%' ORDER BY created_at DESC LIMIT 5")
    rows = cur.fetchall()
    with open("swing_jobs_out.txt", "w") as f:
        f.write("=== Recent Swing Jobs ===\n")
        for r in rows:
            f.write(f"ID: {r[0]} | Type: {r[1]} | Status: {r[2]} | Created: {r[3]} | Error: {r[4]}\n")
    conn.close()
