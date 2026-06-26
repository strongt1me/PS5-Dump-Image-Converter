#!/usr/bin/env python3
"""Fix Unicode symbols in test scripts for Windows PowerShell compatibility"""

import os

def fix_file(filepath):
    """Replace Unicode symbols with ASCII fallback in a file"""
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return False
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count occurrences
    check_count = content.count('✓')
    cross_count = content.count('✗')
    
    # Replace symbols  
    content = content.replace('✓', '{CHECK}')
    content = content.replace('✗', '{CROSS}')
    
    # Add CHECK/CROSS definitions if not present
    if '{CHECK}' in content and 'CHECK =' not in content:
        # Find the first print_check or similar function
        lines = content.split('\n')
        insert_idx = 0
        for i, line in enumerate(lines):
            if 'def print_' in line or 'def print(' in line or 'GREEN =' in line:
                insert_idx = i + 3
                break
        
        # Insert the CHECK/CROSS definitions
        if insert_idx > 0 and 'CHECK =' not in content:
            check_def = "\n# Symbols for Windows compatibility\nCHECK = '[+]'\nCROSS = '[x]'\n\n"
            lines.insert(insert_idx, check_def)
            content = '\n'.join(lines)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✓ Fixed {filepath}: {check_count} ✓ + {cross_count} ✗ replaced")
    return True

# Fix both test scripts
fix_file('test_build_ready.py')
fix_file('.github/skills/release-test/scripts/quick_smoke_test.py')
