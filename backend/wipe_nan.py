import re

file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# 1. Remove all ar = np.nan_to_num(var, nan=0.0) injected lines entirely
text = re.sub(r'^\s*[a-zA-Z0-9_]+\s*=\s*np\.nan_to_num\([a-zA-Z0-9_]+,\s*nan=0\.0\)\s*\n', '', text, flags=re.MULTILINE)

# 2. Inject safe_scalar safely if missing
safe_def = "def safe_scalar(x):\n    import numpy as np\n    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)\n    return float(np.nan_to_num(val, nan=0.0))\n"

if "def safe_scalar(x):" not in text:
    # insert it right after the imports
    text = text.replace("class IntradayTechnicalAnalysis:", safe_def + "\nclass IntradayTechnicalAnalysis:")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("nan stripped and safe_scalar injected.")
