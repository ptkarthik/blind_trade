import sqlite3
import os

db_path = r"C:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\blind_trade.db"

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("SELECT id, type, status, trigger_source, created_at, updated_at FROM jobs WHERE status IN ('pending', 'processing')")
    rows = cursor.fetchall()
    print("STALLED JOBS FOUND:")
    print("ID | Type | Status | Source | Created | Updated")
    print("-" * 60)
    for row in rows:
        print(f"{row[0][:8]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
