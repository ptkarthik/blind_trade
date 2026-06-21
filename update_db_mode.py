import sqlite3
import os

db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "backend", "blind_trade.db"))

def update_schema():
    print(f"Updating database schema at {db_path}...")
    if not os.path.exists(db_path):
        print("Database file not found!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN mode VARCHAR DEFAULT 'swing'")
        print("Added mode to paper_trades")
    except sqlite3.OperationalError as e:
        print(f"paper_trades.mode: {e}")

    try:
        cursor.execute("ALTER TABLE swing_trades ADD COLUMN mode VARCHAR DEFAULT 'swing'")
        print("Added mode to swing_trades")
    except sqlite3.OperationalError as e:
        print(f"swing_trades.mode: {e}")

    conn.commit()
    conn.close()
    print("Schema update completed successfully.")

if __name__ == "__main__":
    update_schema()
