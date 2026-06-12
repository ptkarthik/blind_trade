import sqlite3

def migrate():
    print("Migrating DB...")
    conn = sqlite3.connect('blind_trade.db')
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE swing_trades ADD COLUMN initial_scan_data JSON;")
        print("Successfully added initial_scan_data column to swing_trades.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column initial_scan_data already exists.")
        else:
            print(f"Error: {e}")
            
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
