import sqlite3
import json
import uuid
from datetime import datetime

conn = sqlite3.connect('blind_trade.db')
cursor = conn.cursor()
job_id = "MOCK_SWING_" + str(uuid.uuid4())[:8]
data = [
    {"symbol": "MOCK_BUY.NS", "signal": "BUY", "score": 95, "sector": "Technology", "price": 1500.0},
    {"symbol": "MOCK_SELL.NS", "signal": "SELL", "score": 25, "sector": "Banking", "price": 450.0},
    {"symbol": "MOCK_HOLD.NS", "signal": "NEUTRAL", "score": 55, "sector": "Auto", "price": 820.0}
]
result = {"data": data, "total_scanned": 3, "status_msg": "Completed Mock"}
cursor.execute(
    "INSERT INTO jobs (id, type, status, result, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
    (job_id, "swing_scan", "completed", json.dumps(result), datetime.utcnow().isoformat(), datetime.utcnow().isoformat())
)
conn.commit()
conn.close()
print(f"Mock swing job created: {job_id}")
