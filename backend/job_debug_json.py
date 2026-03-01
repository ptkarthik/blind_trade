import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')
with open('job_debug_json.txt', 'w', encoding='utf-8') as f:
    # Latest swing scan
    r = conn.execute("SELECT result FROM jobs WHERE id='67ffedb8195e4b98a37ffbfd1a005bd3'").fetchone()
    if r:
        f.write(r[0])
