
import sqlite3
import uuid
from datetime import datetime

db_path = "backend/blind_trade.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

job_id = str(uuid.uuid4())
cursor.execute("INSERT INTO jobs (id, type, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?);", 
               (job_id, "intraday", "pending", datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f'), datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')))
conn.commit()
print(f"Created Job {job_id} in PENDING state.")
conn.close()
