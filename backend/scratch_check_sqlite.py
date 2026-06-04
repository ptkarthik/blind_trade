import sqlite3
import datetime

def check_db():
    conn = sqlite3.connect("blind_trade.db")
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    c.execute("SELECT id, type, status, trigger_source, created_at FROM jobs ORDER BY created_at DESC LIMIT 10")
    rows = c.fetchall()
    
    print(f"Top 10 Jobs from SQLite:")
    for r in rows:
        print(dict(r))

    c.execute("SELECT id, type, status, trigger_source, created_at FROM jobs WHERE status IN ('pending', 'processing', 'running')")
    active = c.fetchall()
    print(f"\nActive/Stuck Jobs ({len(active)}):")
    for r in active:
        print(dict(r))
        
if __name__ == "__main__":
    check_db()
