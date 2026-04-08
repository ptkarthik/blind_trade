import sqlite3
import os

db_path = "app.db"
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT symbol, score, signal, created_at FROM results WHERE signal='BUY' ORDER BY id DESC LIMIT 10;")
        rows = cursor.fetchall()
        print(f"--- 🏁 Recent V12.1 BUY Signals ({len(rows)}) ---")
        for row in rows:
            print(f"Symbol: {row[0]} | Score: {row[1]} | Signal: {row[2]} | Time: {row[3]}")
    except Exception as e:
        print(f"Query Error: {str(e)}")
    conn.close()
else:
    print(f"DB not found at {os.path.abspath(db_path)}")
