import os
import re
import glob

# Search for all python files in the services directory
target_files = glob.glob('c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/*.py')

pattern = re.compile(r"float\(([\w_]+)\.iloc\[0\]\) if hasattr\(\1, ['\x22]iloc['\x22]\) else float\(\1\)")

total_replaced = 0

for file_path in target_files:
    if 'Copy' in file_path: continue
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content, num_subs = pattern.subn(r"safe_scalar(\1)", content)
    
    if num_subs > 0:
        total_replaced += num_subs
        
        # Inject safe_scalar definition if missing
        if 'def safe_scalar' not in new_content and 'safe_scalar' in new_content:
            safe_scalar_def = "\n\ndef safe_scalar(x):\n    return float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)\n"
            
            # Find a safe place to inject (after initial imports)
            insert_idx = 0
            for ext in ['import pandas', 'import numpy', 'import time']:
                idx = new_content.find(ext)
                if idx != -1:
                    insert_idx = max(insert_idx, new_content.find('\n', idx) + 1)
            
            if insert_idx == 0: insert_idx = new_content.find('\n') + 1
            
            new_content = new_content[:insert_idx] + safe_scalar_def + new_content[insert_idx:]

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Replaced {num_subs} in {os.path.basename(file_path)}")

print(f"Done. {total_replaced} total replacements.")
