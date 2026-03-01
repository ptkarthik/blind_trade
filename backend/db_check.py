import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')

with open('db_out.txt', 'w', encoding='utf-8') as f:
    def check(t):
        r = conn.execute(f"SELECT created_at, result FROM jobs WHERE type='{t}' AND status='completed' ORDER BY created_at DESC LIMIT 1").fetchone()
        if r and r[1]: 
            try:
                d = json.loads(r[1]).get('data', [])
                if d:
                    symbols = [x.get("symbol") for x in d[:5]]
                    f.write(f'{t} Latest: {r[0]}\n')
                    f.write(f'Count: {len(d)}\n')
                    f.write(f'Top 5: {symbols}\n\n')
                else:
                    f.write(f'{t} Latest: {r[0]} - Data array is empty\n\n')
            except Exception as e:
                f.write(f'{t} Failed to parse JSON: {e}\n\n')
        else: 
            f.write(f'{t} No completed jobs or no result\n\n')

    f.write("--- DB Verification --\n")
    check('intraday')
    check('swing_scan')
    check('full_scan')
    f.write("-----------------------\n")
