import sqlite3, json, os

db_path = 'backend/blind_trade.db'
if not os.path.exists(db_path):
    print("DB not found")
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()
c.execute("SELECT result FROM jobs WHERE type='swing_scan' AND status='completed' ORDER BY updated_at DESC LIMIT 1")
row = c.fetchone()
if row:
    data = json.loads(row[0])
    stocks = data.get('data', [])
    # Sort by score descending
    stocks.sort(key=lambda x: x.get('score', 0), reverse=True)
    for i, s in enumerate(stocks[:5]):
        sym = s.get('symbol','?')
        score = s.get('score', 0)
        signal = s.get('signal','')
        strategy = s.get('strategy','')
        price = s.get('price', 0)
        reasons = s.get('reasons', [])
        print(f'\n=== #{i+1}: {sym} | Score: {score} | {signal} | {strategy} | Price: {price} ===')
        for r in reasons:
            print(f'  [{r.get("type","?"):>8}] {r.get("impact",0):>+3} | {r.get("text","")}')
        # Extra fields
        for k in ['vol_ratio','vol_5d_avg','vol_3d_avg','delivery_pct','adx','stock_20d_return','conviction','setup_type','confidence','stop_loss','target','is_near_20d_high']:
            if k in s:
                print(f'  >> {k}: {s[k]}')
else:
    print('No completed swing scan found')
conn.close()
