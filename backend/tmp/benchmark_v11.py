import sqlite3
from datetime import datetime

def check_performance():
    conn = sqlite3.connect('blind_trade.db')
    cursor = conn.cursor()
    cursor.execute("SELECT created_at, updated_at, id FROM jobs WHERE type='intraday' AND status='completed' ORDER BY updated_at DESC LIMIT 1;")
    row = cursor.fetchone()
    conn.close()

    if not row:
        print("❌ No completed intraday jobs found in SQLite.")
        return

    # Handle both string and datetime objects (depending on how sqlite returns them)
    try:
        start = datetime.fromisoformat(row[0].replace('Z', '+00:00')) if isinstance(row[0], str) else row[0]
        end = datetime.fromisoformat(row[1].replace('Z', '+00:00')) if isinstance(row[1], str) else row[1]
    except:
        # Fallback for older sqlite versions or weird formats
        start = row[0]
        end = row[1]

    print(f"\n📊 --- [V11 ALPHA-PULSE BENCHMARK] ---")
    print(f"🔹 Job ID:    {row[2]}")
    print(f"🔹 Started:   {start}")
    print(f"🔹 Completed: {end}")
    
    # Try custom calculation if possible
    try:
        duration = end - start
        print(f"🚀 TOTAL RUN TIME: {duration}")
    except:
        print(f"🚀 TOTAL RUN TIME: (Check Start/End Difference)")
    print(f"--------------------------------------\n")

if __name__ == "__main__":
    check_performance()
