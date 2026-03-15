
import sqlite3
import os

db_path = "backend/blind_trade.db"
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT id, type, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 5;")
rows = cursor.fetchall()

print("Latest 5 Jobs:")
for row in rows:
    print(row)

conn.close()
