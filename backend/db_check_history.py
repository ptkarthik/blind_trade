import sqlite3

conn = sqlite3.connect('blind_trade.db')
with open('db_out_history.txt', 'w', encoding='utf-8') as f:
    rows = conn.execute("SELECT id, created_at, status, updated_at, json_extract(result, '$.data') IS NOT NULL as has_data FROM jobs WHERE type='swing_scan' ORDER BY updated_at DESC LIMIT 10").fetchall()
    f.write(str(rows))
