import sqlite3
conn = sqlite3.connect('backend/blind_trade.db')
cur = conn.cursor()
cur.execute('SELECT result FROM jobs WHERE type="intraday" ORDER BY updated_at DESC LIMIT 1')
print(cur.fetchone()[0])
