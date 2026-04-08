file_path = "c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/ta_intraday.py"
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("([df['close'].iloc[-1] if len([df['close']) > 0 else 0.0)]", "[(df['close'].iloc[-1] if len(df['close']) > 0 else 0.0)]")
text = text.replace("len([df['close'])", "len(df['close'])")

# Also check for any other len([xx) 
import re
text = re.sub(r'len\(\[([a-zA-Z0-9_\[\]\'\"]+)\)', r'len(\1)', text)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("Syntax fixed")
