with open('c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
with open('divs.txt', 'w', encoding='utf-8') as f:
    for i, line in enumerate(lines):
        if '/' in line:
            f.write(f'{i+1}: {line.strip()}\n')
