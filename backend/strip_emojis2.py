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
            
            # Find and replace all emojis
            if emoji_pattern.search(content):
                modified = emoji_pattern.sub('', content)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(modified)
                count += 1

print(f"Removed emojis from {count} files completely.")
