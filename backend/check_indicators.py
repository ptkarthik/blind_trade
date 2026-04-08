with open('c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if '_val = ' in line and ('ema' in line or 'atr' in line or 'vwap' in line or 'adx' in line or 'vol_ma' in line):
        print(f'{i+1}: {line.strip()}')
