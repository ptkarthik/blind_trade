
import sqlite3
import os

def check():
    db_path = os.path.join(os.getcwd(), "blind_trade.db")
    if not os.path.exists(db_path):
        print(f"DB not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    ids = [
        '6961861d-cc83-4653-9d9f-1a7054695edf', 
        'd1344a0a-9e68-4b86-b50f-514cdd3e116c'
    ]
    
    print("-" * 50)
    for jid in ids:
        clean_id = jid.replace("-", "")
        cursor.execute("SELECT id, type, status, created_at, updated_at FROM jobs WHERE id = ?", (clean_id,))
        row = cursor.fetchone()
        if row:
            print(f"ID: {row[0]}")
            print(f"TYPE: {row[1]}")
            print(f"STATUS: {row[2]}")
            print(f"CREATED: {row[3]}")
            print(f"UPDATED: {row[4]}")
            print("-" * 50)
        else:
            # Maybe the ID in DB is stored with hyphens? 
            cursor.execute("SELECT id, type, status, created_at, updated_at FROM jobs WHERE id = ?", (jid,))
            row = cursor.fetchone()
            if row:
                print(f"ID: {row[0]}")
                print(f"TYPE: {row[1]}")
                print(f"STATUS: {row[2]}")
                print(f"CREATED: {row[3]}")
                print(f"UPDATED: {row[4]}")
                print("-" * 50)
            else:
                print(f"Job {jid} not found")
    conn.close()

if __name__ == "__main__":
    check()
