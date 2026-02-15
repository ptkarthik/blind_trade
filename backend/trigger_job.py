
import sqlite3
import uuid
import datetime

def trigger_job():
    try:
        conn = sqlite3.connect('blind_trade.db')
        cursor = conn.cursor()
        job_id = uuid.uuid4().hex
        cursor.execute(
            "INSERT INTO jobs (id, type, status, created_at) VALUES (?, ?, ?, ?)",
            (job_id, "full_scan", "pending", datetime.datetime.now())
        )
        conn.commit()
        conn.close()
        print(f"Job Triggered: {job_id}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    trigger_job()
