import sqlite3
import pandas as pd

conn = sqlite3.connect("backend/blind_trade.db")
query = "SELECT * FROM trap_patterns ORDER BY id DESC LIMIT 5"
df = pd.read_sql_query(query, conn)
print(df.to_string())
conn.close()
