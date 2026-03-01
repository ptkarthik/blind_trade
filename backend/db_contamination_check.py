import sqlite3

conn = sqlite3.connect('blind_trade.db')
with open('db_contamination_check.txt', 'w', encoding='utf-8') as f:
    rows = conn.execute("SELECT id, type, updated_at FROM jobs WHERE result LIKE '%3MINDIA.NS%'").fetchall()
    f.write(f"Jobs containing 3MINDIA.NS:\n")
    for r in rows:
        f.write(f"{r}\n")
