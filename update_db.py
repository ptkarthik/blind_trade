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

    # Update paper_trades
    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN highest_price_reached FLOAT")
        print("Added highest_price_reached to paper_trades")
    except sqlite3.OperationalError as e:
        print(f"paper_trades.highest_price_reached: {e}")

    try:
        cursor.execute("ALTER TABLE paper_trades ADD COLUMN trailing_sl_percent FLOAT DEFAULT 3.0")
        print("Added trailing_sl_percent to paper_trades")
    except sqlite3.OperationalError as e:
        print(f"paper_trades.trailing_sl_percent: {e}")

    # Update swing_trades
    try:
        cursor.execute("ALTER TABLE swing_trades ADD COLUMN highest_price_reached FLOAT")
        print("Added highest_price_reached to swing_trades")
    except sqlite3.OperationalError as e:
        print(f"swing_trades.highest_price_reached: {e}")

    try:
        cursor.execute("ALTER TABLE swing_trades ADD COLUMN trailing_sl_percent FLOAT DEFAULT 3.0")
        print("Added trailing_sl_percent to swing_trades")
    except sqlite3.OperationalError as e:
        print(f"swing_trades.trailing_sl_percent: {e}")

    conn.commit()
    conn.close()
    print("Schema update completed successfully.")

if __name__ == "__main__":
    update_schema()
