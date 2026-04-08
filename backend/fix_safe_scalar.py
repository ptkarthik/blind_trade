import os
import re

services_dir = 'c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app/services/'

for file in os.listdir(services_dir):
    if file.endswith('.py'):
        path = os.path.join(services_dir, file)
        with open(path, 'r', encoding='utf-8') as f:
            text = f.read()
            
        # Target anything under def safe_scalar(x):
        # We replace "def safe_scalar(x):\n    return safe_scalar(x)" everywhere.
        # But wait, ta_swing might have "def safe_scalar(x):\n    return float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)"
        # Or maybe it has "def safe_scalar(x):\n    return safe_scalar(x)".
        
        # We use regex to replace the whole function definition and first line of its body.
        pattern = re.compile(r'def safe_scalar\(x\):\s*\n\s*return.*?\n')
        
        new_def = "def safe_scalar(x):\n    import numpy as np\n    val = float(x.iloc[0]) if hasattr(x, 'iloc') else float(x)\n    return float(np.nan_to_num(val, nan=0.0))\n"
        
        if pattern.search(text):
            text = pattern.sub(new_def, text)
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f'Standardized safe_scalar in {file}')
