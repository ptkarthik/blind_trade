
import sqlite3
import uuid
import datetime
import os
import time

def clear_pending_jobs():
    conn = sqlite3.connect('blind_trade.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE jobs SET status = 'cancelled' WHERE status = 'pending'")
    conn.commit()
    conn.close()
    print("Pending jobs cleared.")

def trigger_job(job_type):
    try:
        conn = sqlite3.connect('blind_trade.db')
        cursor = conn.cursor()
        job_id = uuid.uuid4().hex
        cursor.execute(
            "INSERT INTO jobs (id, type, status, created_at) VALUES (?, ?, ?, ?)",
            (job_id, job_type, "pending", datetime.datetime.now())
        )
        conn.commit()
        conn.close()
        print(f"{job_type} Job Triggered: {job_id}")
        return job_id
    except Exception as e:
        print(f"Error triggering {job_type}: {e}")
        return None

if __name__ == "__main__":
    clear_pending_jobs()
    trigger_job("full_scan")
    trigger_job("intraday")
