import sqlite3
conn = sqlite3.connect('blind_trade.db')
cursor = conn.cursor()
cursor.execute("SELECT id, status, updated_at FROM jobs WHERE type = 'swing_scan' ORDER BY updated_at DESC LIMIT 5")
for row in cursor.fetchall():
    print(row)
conn.close()
