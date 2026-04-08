import sqlite3
import os

db_path = "app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, type, status, created_at FROM jobs WHERE status != 'completed' ORDER BY id DESC LIMIT 10;")
        rows = cursor.fetchall()
        print("--- 🕵️‍♂️ Active Jobs Audit ---")
        if not rows:
            print("No active jobs found.")
        for row in rows:
            print(f"ID: {row[0]} | Type: {row[1]} | Status: {row[2]} | Time: {row[3]}")
    except Exception as e:
        print(f"Query Error: {str(e)}")
    conn.close()
else:
    print(f"DB not found at {os.path.abspath(db_path)}")
