import sqlite3
import os

db_path = r"C:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\blind_trade.db"

if not os.path.exists(db_path):
    print(f"Error: Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    cursor.execute("ALTER TABLE jobs ADD COLUMN trigger_source TEXT DEFAULT 'manual'")
    conn.commit()
    print("Column 'trigger_source' added successfully.")
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e).lower():
        print("Column 'trigger_source' already exists.")
    else:
        print(f"SQLite Error: {e}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()
