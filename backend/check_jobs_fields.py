import sqlite3
import json

conn = sqlite3.connect('blind_trade.db')
c = conn.cursor()

for job_type in ['full_scan', 'intraday']:
    c.execute('SELECT id, updated_at, result FROM jobs WHERE type = ? AND result IS NOT NULL ORDER BY updated_at DESC LIMIT 5', (job_type,))
    rows = c.fetchall()
    found = False
    for row in rows:
        try:
            res = json.loads(row[2])
            data = res.get('data', [])
            if data:
                print(f'\n--- {job_type} ({row[1]}) ---')
                d = data[0]
                print('symbol:', d.get('symbol'))
                print('analysis_mode:', d.get('analysis_mode'))
                print('strategic_summary:', d.get('strategic_summary'))
                print('intraday_signal:', d.get('intraday_signal', 'N/A'))
                print('holding_period:', d.get('investment_advisory', {}).get('holding_period', {}) if d.get('investment_advisory') else 'N/A')
                found = True
                break
        except Exception as e:
            print('Error parsing', job_type, e)
    if not found:
        print(f'\n--- No data found for {job_type} ---')
