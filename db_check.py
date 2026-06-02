import sqlite3
import pandas as pd
conn = sqlite3.connect('backend/blind_trade.db')
df = pd.read_sql_query("SELECT id, symbol, status, product_type, qty, buy_price, sell_price, stop_loss, target, close_reason FROM paper_trades WHERE symbol LIKE '%APOLLO%';", conn)
print(df.to_string())
