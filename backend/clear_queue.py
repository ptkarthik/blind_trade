
import sqlite3

def clear_queue():
    try:
        conn = sqlite3.connect('blind_trade.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE jobs SET status = 'failed', error_details = 'Force Reset' WHERE status IN ('pending', 'processing')")
        conn.commit()
        count = cursor.rowcount
        conn.close()
        print(f"Queue Cleared. {count} jobs reset.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    clear_queue()
