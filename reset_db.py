import sqlite3
import os

def reset_database():
    """
    [V10] Clean-Slate Reset Script. 🕵️‍♂️🚨
    Clears all 'ghost' jobs from the database during startup.
    """
    db_path = "blind_trade.db"
    
    if not os.path.exists(db_path):
        # Check in backend folder if not in root
        db_path = os.path.join("backend", "blind_trade.db")
        
    if not os.path.exists(db_path):
        print("⚠️ Database not found. Skipping SQL sync.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Reset 'processing' jobs to 'stopped'
        cursor.execute("UPDATE jobs SET status = 'stopped' WHERE status = 'processing'")
        rows_reset = cursor.rowcount
        
        # 2. Cleanup any partial results for a perfectly fresh dashboard
        cursor.execute("UPDATE jobs SET result = NULL WHERE status = 'stopped'")
        
        conn.commit()
        conn.close()
        
        if rows_reset > 0:
            print(f"✅ Clean-Slate Success: {rows_reset} ghost jobs reset to 'Stopped'.")
        else:
            print("✅ Clean-Slate Success: No ghost jobs found.")
            
    except Exception as e:
        print(f"❌ Clean-Slate Error: {e}")

if __name__ == "__main__":
    print("🛰️ Blind Trade: Cleaning Database Ghosts...")
    reset_database()
