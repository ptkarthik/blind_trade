import sqlite3
import pprint

conn = sqlite3.connect('blind_trade.db')
c = conn.cursor()
c.execute("SELECT id, error_details, updated_at FROM jobs WHERE type = 'full_scan' AND status = 'failed' ORDER BY updated_at DESC LIMIT 5")
rows = c.fetchall()
for r in rows:
    print(f"ID: {r[0]}")
    print(f"Error: {r[1]}")
    print(f"Updated: {r[2]}")
    print("-" * 50)
