file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

import re
text = re.sub(r'^(dict|float|list|pd\.Series|dict\s*\|\s*None)\s*if df is None', r'        if df is None', text, flags=re.MULTILINE)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Indentation fixed")
