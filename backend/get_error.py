import sqlite3
db = sqlite3.connect('blind_trade.db')
cursor = db.cursor()
cursor.execute("SELECT error_details FROM jobs WHERE id='ecb08a9230144f94a5911c4673ddfd0a'")
print(cursor.fetchone()[0])
