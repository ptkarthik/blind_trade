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
    
    print(f"{'Rank':<4} | {'Symbol':<12} | {'Backend Score':<13} | {'UI Reasons Sum':<14} | {'Discrepancy'}")
    print("-" * 70)
    for i, s in enumerate(stocks[:10]):
        sym = s.get('symbol','?')
        score = s.get('score', 0)
        reasons = s.get('reasons', [])
        
        # Calculate UI reasons sum
        # In the UI, each reason has an 'impact' which is added if 'type' is 'positive' 
        # and subtracted if 'type' is 'negative'. The value in 'impact' is already signed in our logic?
        # Let's check: in swing_engine.py, impact is passed as a number (sometimes positive, sometimes negative).
        ui_sum = sum([r.get('impact', 0) for r in reasons])
        
        diff = ui_sum - score
        print(f"{i+1:<4} | {sym:<12} | {score:<13} | {ui_sum:<14} | {diff}")
else:
    print('No completed swing scan found')
conn.close()
