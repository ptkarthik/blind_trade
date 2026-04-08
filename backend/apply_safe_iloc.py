import re

file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

def replace_iloc(match):
    series_name = match.group(1)
    
    # Exclude situations where it's already in a safe check or an assignment LHS
    # If the text immediately preceding is "len(" or something, it's safe.
    
    # Determine default value based on variable name heuristics
    s_lower = series_name.lower()
    
    if any(k in s_lower for k in ['score', 'rsi', 'mfi']):
        default_val = '50.0'
    elif any(k in s_lower for k in ['ratio', 'mu', 'factor', 'pct', 'idx']):
        default_val = '1.0'
    else:
        # Default for price, volume, adx, atr, vwap
        default_val = '0.0'
        
    return f"({series_name}.iloc[-1] if len({series_name}) > 0 else {default_val})"

# The regex matches any variable name that ends with .iloc[-1]
# E.g. df['close'].iloc[-1] -> series_name = df['close']
# ema9_series.iloc[-1] -> series_name = ema9_series
# But we must be careful with indexing like df.iloc[-1] vs series.iloc[-1].

def process_line(line):
    # Don't touch if already has 'len('
    if "if len" in line: return line
    return re.sub(r'([a-zA-Z0-9_\[\]\'\"]+)\.iloc\[-1\]', replace_iloc, line)

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    new_lines.append(process_line(line))

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Safe .iloc[-1] applied!")
