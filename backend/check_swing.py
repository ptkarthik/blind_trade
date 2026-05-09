import sqlite3, json

conn = sqlite3.connect('blind_trade.db')
c = conn.cursor()

for job_id in ['46adc65a-0029-4b08-ad54-ac59691d6517', '997e2e4b-e883-42e1-9be3-64d9184cf2cc']:
    c.execute('SELECT result, created_at FROM jobs WHERE id=?', (job_id,))
    row = c.fetchone()
    if not row or not row[0]: continue
    data = json.loads(row[0])
    ts = row[1]
    scanned = data.get('total_scanned', data.get('progress', '?'))
    raw = data.get('raw_signal_count', len(data.get('data', [])))
    plan = data.get('trade_plan_count', '?')
    msg = data.get('status_msg', '')
    d = data.get('data', [])
    print(f"Job {job_id[:8]} | {ts} | Scanned:{scanned} | Raw:{raw} | Plan:{plan} | Data:{len(d)}")
    for s in d[:5]:
        sym = s.get('symbol', '?')
        score = s.get('score', '?')
        sig = s.get('signal', '?')
        strat = s.get('strategy', '?')
        print(f"  {sym} | {score} | {sig} | {strat}")

conn.close()
