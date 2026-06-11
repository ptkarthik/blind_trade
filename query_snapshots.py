import sqlite3
import pandas as pd

conn = sqlite3.connect("backend/blind_trade.db")
query = """
SELECT symbol, strategy, entry_price, eod_price, stop_loss, eod_change_pct, performance_tag
FROM scan_snapshots 
WHERE scan_date = date('now') AND performance_tag = 'TRAP'
"""
df = pd.read_sql_query(query, conn)
print(df.to_string())
conn.close()
