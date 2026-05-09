import os

def find_penalties(filepath, out_f):
    out_f.write(f"\n--- Penalties in {os.path.basename(filepath)} ---\n")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                line_lower = line.lower()
                if 'penalty' in line_lower or 'deduct' in line_lower or 'score -=' in line_lower or '-25' in line or 'impact\": -' in line:
                    out_f.write(f"L{i+1}: {line.strip()}\n")
    except Exception as e:
        out_f.write(f"Error reading {filepath}: {e}\n")

files = [
    r'c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\ta_intraday.py',
    r'c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\intraday_engine.py',
    r'c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\scanner_engine.py',
    r'c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\fundamentals.py',
    r'c:\Users\Karthik\.gemini\antigravity\scratch\blind_trade\backend\app\services\institutional_intel.py'
]

with open('penalties_output.txt', 'w', encoding='utf-8') as out_f:
    for file in files:
        if os.path.exists(file):
            find_penalties(file, out_f)
