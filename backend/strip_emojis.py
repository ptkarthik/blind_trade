import os
import re

emoji_pattern = re.compile(r'[\U00010000-\U0010ffff\u2600-\u27BF\u2300-\u23FF]')

count = 0
for root, dirs, files in os.walk('c:/Users/Karthik/.gemini/antigravity/scratch/blind_trade/backend/app'):
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find lines with print and emoji
            lines = content.split('\n')
            modified = False
            for i, line in enumerate(lines):
                if 'print(' in line and emoji_pattern.search(line):
                    # Remove emojis from the print line
                    safe_line = emoji_pattern.sub('', line)
                    lines[i] = safe_line
                    modified = True
                    count += 1
            
            if modified:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))

print(f"Removed emojis from {count} print statements.")
