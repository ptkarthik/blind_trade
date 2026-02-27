import sqlite3
import pprint

conn = sqlite3.connect('blind_trade.db')
c = conn.cursor()
c.execute("SELECT id, error_details, updated_at FROM jobs WHERE type = 'intraday' AND status = 'failed' ORDER BY updated_at DESC LIMIT 5")
rows = c.fetchall()

for row in rows:
    print(f"ID: {row[0]}")
    print(f"Error: {row[1]}")
    print(f"Updated: {row[2]}")
    print("-" * 50)
