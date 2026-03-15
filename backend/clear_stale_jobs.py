
import sqlite3
import os

db_path = "backend/blind_trade.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check everything
cursor.execute("SELECT id, type, status, created_at FROM jobs ORDER BY created_at DESC LIMIT 10;")
rows = cursor.fetchall()

print("Full History (Last 10):")
for row in rows:
    print(row)

# Specifically look for stale jobs blocking new ones
cursor.execute("SELECT id, type, status, created_at FROM jobs WHERE status IN ('pending', 'processing');")
stale = cursor.fetchall()

if stale:
    print("\n⚠️ Found Stale Jobs:")
    for row in stale:
        print(row)
    
    print("\n🧹 Clearing stale jobs...")
    cursor.execute("UPDATE jobs SET status = 'failed', error_details = 'Stale job cleared during system recovery' WHERE status IN ('pending', 'processing');")
    conn.commit()
    print("✅ All stale jobs marked as 'failed'.")
else:
    print("\nNo stale jobs found.")

conn.close()
