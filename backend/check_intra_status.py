import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')
c = conn.cursor()
c.execute("SELECT id, status, result, error_details, updated_at FROM jobs WHERE type = 'intraday' ORDER BY updated_at DESC LIMIT 5")
for row in c.fetchall():
    print('ID:', row[0][:8], 'Status:', row[1], 'Updated:', row[4])
    r = row[2]
    if r:
        try:
            p_res = json.loads(r)
            print('  Progress:', p_res.get('progress'), '/', p_res.get('total_steps'))
            print('  Msg:', p_res.get('status_msg'))
        except (ValueError, TypeError): pass
    if row[3]: print('  Err:', row[3])
    print('-'*30)
