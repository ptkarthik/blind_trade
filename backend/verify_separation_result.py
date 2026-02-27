
import sqlite3
import pandas as pd

def check_jobs():
    conn = sqlite3.connect('blind_trade.db')
    df = pd.read_sql_query("SELECT id, type, status, updated_at FROM jobs ORDER BY created_at DESC LIMIT 5", conn)
    conn.close()
    print(df.to_string())

if __name__ == "__main__":
    check_jobs()
