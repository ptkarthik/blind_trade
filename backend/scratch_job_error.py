import sqlite3

def check_error():
    conn = sqlite3.connect("blind_trade.db")
    c = conn.cursor()
    c.execute("SELECT created_at, error_details FROM jobs WHERE status='failed' ORDER BY created_at DESC LIMIT 5")
    rows = c.fetchall()
    
    for r in rows:
        print(f"Time: {r[0]}, Error: {r[1]}")
        
if __name__ == "__main__":
    check_error()
