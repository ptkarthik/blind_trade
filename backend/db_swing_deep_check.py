import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')

with open('db_swing_deep_check.txt', 'w', encoding='utf-8') as f:
    rows = conn.execute("SELECT id, created_at, status, updated_at, result FROM jobs WHERE type='swing_scan' ORDER BY updated_at DESC").fetchall()
    f.write(f"Found {len(rows)} swing_scan jobs\n\n")
    for r in rows:
        jid, created, status, updated, result = r
        count = 0
        top_syms = []
        if result:
            try:
                res_obj = json.loads(result)
                data = res_obj.get('data', [])
                count = len(data)
                top_syms = [x.get('symbol') for x in data[:3]]
            except:
                count = -1
        f.write(f"ID: {jid} | Created: {created} | Status: {status} | Updated: {updated} | Count: {count} | Top: {top_syms}\n")
