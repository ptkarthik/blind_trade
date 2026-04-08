
import sqlite3
import os

# Database Path (Relative to execution)
# backend/app/core/config.py says it's in the 'backend' folder
db_path = os.path.join("backend", "blind_trade.db")

if os.path.exists(db_path):
    print(f"--- 🛠️  Checking local DB: {db_path} ---")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(paper_trades)")
        rows = cursor.fetchall()
        if not rows:
             print("❌ Table 'paper_trades' not found in this DB.")
             # List tables for debug
             cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
             print(f"Available tables: {[r[0] for r in cursor.fetchall()]}")
        else:
            columns = [row[1] for row in rows]
            if "close_reason" not in columns:
                print("⚓ Adding 'close_reason' column to 'paper_trades'...")
                cursor.execute("ALTER TABLE paper_trades ADD COLUMN close_reason VARCHAR;")
                conn.commit()
                print("✅ Column added successfully.")
            else:
                print("ℹ️  'close_reason' column already exists.")
            
    except Exception as e:
        print(f"❌ DB Repair Error: {e}")
    finally:
        conn.close()
else:
    print(f"⚠️  DB {db_path} not found. Skipping migration.")
