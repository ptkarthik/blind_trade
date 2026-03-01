import sqlite3

conn = sqlite3.connect('blind_trade.db')
with open('db_zombie_hunt.txt', 'w', encoding='utf-8') as f:
    # Look for anything updated on Feb 28
    rows = conn.execute("SELECT id, type, status, updated_at FROM jobs WHERE updated_at LIKE '2026-02-28 15:%' ORDER BY updated_at").fetchall()
    f.write(f"Jobs updated between 15:00 and 16:00 UTC on Feb 28:\n")
    for r in rows:
        f.write(f"{r}\n")
