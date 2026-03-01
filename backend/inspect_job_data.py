import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')
cursor = conn.cursor()
cursor.execute("SELECT result FROM jobs WHERE id = '67ffedb8195e4b98a37ffbfd1a005bd3'")
row = cursor.fetchone()
if row:
    result = json.loads(row[0])
    data = result.get("data", [])
    print(f"Data length: {len(data)}")
    for item in data:
        print(f"Symbol: {item.get('symbol')} | Signal: {item.get('signal')} | Score: {item.get('score')}")
conn.close()
