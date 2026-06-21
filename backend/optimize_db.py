import sqlite3
import os
import time

def optimize_db():
    db_path = "blind_trade.db"
    
    if not os.path.exists(db_path):
        db_path = os.path.join("backend", "blind_trade.db")
        
    if not os.path.exists(db_path):
        print("Database not found! Run this script in the backend directory.")
        return

    print("[*] Starting Database Optimization for Lightning Speed...")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Add Compound Indexes for our exact query patterns
        print("[*] Creating compound indexes...")
        
        try:
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_jobs_perf_signals 
            ON jobs (type, status, created_at)
            """)
        except Exception as e:
            print(f"[-] Could not create compound index: {e}")
            
        try:
            cursor.execute("""
            CREATE INDEX IF NOT EXISTS ix_jobs_updated_at 
            ON jobs (updated_at)
            """)
        except Exception as e:
            print(f"[-] Could not create updated_at index: {e}")
        
        # 2. Rebuild Database (VACUUM) to remove fragmentation
        print("[*] Vacuuming database to reclaim space and defragment...")
        start_time = time.time()
        cursor.execute("VACUUM;")
        
        # 3. Optimize SQLite PRAGMAs for performance
        cursor.execute("PRAGMA optimize;")
        
        conn.commit()
        conn.close()
        
        elapsed = time.time() - start_time
        print(f"[*] Optimization complete in {elapsed:.2f} seconds!")
        print("[*] The database is now tuned for maximum query speed.")
        
    except Exception as e:
        print(f"[!] Error during optimization: {e}")

if __name__ == "__main__":
    optimize_db()
