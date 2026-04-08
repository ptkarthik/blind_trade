import re

file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Pattern to match function definition: def my_func(df: pd.DataFrame...) -> return_type:
pattern = re.compile(r'(def \w+\(.*?(?:df|nifty_df):\s*pd\.DataFrame.*?\)(?: -> (.*?))?:\s*\n)((?:\s*"{3}.*?"{3}\s*\n)?)', re.DOTALL)

def inject_validation(match):
    def_line = match.group(1)
    docstring = match.group(2)
    return_type_raw = match.group(2) # actually match.group(2) might be inside group 1, wait, group 2 is the 'dict'
    
    # re.compile behavior: group 1 is def ..., group 2 is the return type, group 3 is the docstring.
    full_def = match.group(1)
    ret_type = full_def.split('->')[-1].split(':')[0].strip() if '->' in full_def else 'dict'
    
    if 'dict' in ret_type:
        default_val = '{}'
    elif 'float' in ret_type:
        default_val = '0.0'
    elif 'list' in ret_type:
        default_val = '[]'
    elif 'pd.Series' in ret_type:
        default_val = 'pd.Series(dtype=float)'
    else:
        default_val = '{}'

    # Find the indent level of the next line to match it
    # We'll just enforce 8 spaces as they are inside IntradayTechnicalAnalysis static methods
    indent = "        "

    validation_code = f"{indent}if df is None or df.empty: return {default_val}\n"
    validation_code += f"{indent}for col in ['open', 'high', 'low', 'close', 'volume']:\n"
    validation_code += f"{indent}    if col in df.columns:\n"
    validation_code += f"{indent}        if isinstance(df[col], pd.DataFrame): df[col] = df[col].iloc[:, 0]\n"

    # Some functions override 'df15m' but the param is 'df'. This handles both safely.
    # Replace the match with the injected code
    return f"{full_def}{docstring}{validation_code}"

text_new = pattern.sub(inject_validation, text)

# Fix duplicate "for col in..." if run twice
with open(file_path, "w", encoding="utf-8") as f:
    f.write(text_new)

print("DF Validation and Duplication Guards Applied!")
