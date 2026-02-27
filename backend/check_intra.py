import sqlite3
db = sqlite3.connect('blind_trade.db')
cursor = db.cursor()
cursor.execute("SELECT status, error_details FROM jobs WHERE type='intraday_scan' ORDER BY created_at DESC LIMIT 1")
print(cursor.fetchone())
