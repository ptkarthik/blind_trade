import sqlite3
import pprint
db = sqlite3.connect('blind_trade.db')
cursor = db.cursor()
cursor.execute("SELECT id, type, status, created_at, error_details FROM jobs WHERE type='swing_scan' ORDER BY created_at DESC LIMIT 5")
rows = cursor.fetchall()
for r in rows:
    print(r)
