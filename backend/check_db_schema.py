import sqlite3

def get_schema():
    conn = sqlite3.connect('blind_trade.db')
    c = conn.cursor()
    c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='jobs'")
    row = c.fetchone()
    if row:
        print(row[0])
    else:
        print("Table 'jobs' not found.")
    conn.close()

get_schema()
