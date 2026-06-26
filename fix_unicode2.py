#!/usr/bin/env python3
"""Fix Unicode symbols in test scripts - proper version"""

import re

def fix_test_file(filepath):
    """Replace {CHECK} and {CROSS} with proper variable references"""
    print(f"Fixing {filepath}...")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ensure CHECK/CROSS are defined
    if 'CHECK =' not in content:
        # Find where to insert
        insert_line = """
# Windows-compatible symbols
CHECK = '[+]'
CROSS = '[x]'

"""
        # Insert after imports and color definitions
        import_end = content.rfind('RESET = ')
        if import_end > 0:
            end_of_line = content.find('\n', import_end)
            content = content[:end_of_line+1] + insert_line + content[end_of_line+1:]
    
    # Replace {CHECK} and {CROSS} with f-string references
    content = re.sub(r'\{CHECK\}', '{CHECK}', content)  # Keep for now
    content = re.sub(r'\{CROSS\}', '{CROSS}', content)  # Keep for now
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ {filepath} fixed")

# Fix both files
fix_test_file('test_build_ready.py')
fix_test_file('.github/skills/release-test/scripts/quick_smoke_test.py')

# Verify
print("\nVerification:")
with open('test_build_ready.py') as f:
    content = f.read()
    print(f"test_build_ready.py: CHECK defined = {'CHECK =' in content}, {CHECK} used = {'{CHECK}' in content}")

with open('.github/skills/release-test/scripts/quick_smoke_test.py') as f:
    content = f.read()
    print(f"quick_smoke_test.py: CHECK defined = {'CHECK =' in content}, {CHECK} used = {'{CHECK}' in content}")
