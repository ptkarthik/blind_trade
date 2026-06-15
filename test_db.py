import sqlite3
conn = sqlite3.connect('backend/blind_trade.db')
c = conn.cursor()
c.execute("SELECT id, type, status, trigger_source, error_details, created_at, updated_at FROM jobs WHERE type = 'full_scan' ORDER BY created_at DESC LIMIT 5")
for r in c.fetchall():
    print(r)
conn.close()
