#!/usr/bin/env python3
"""
Code-Cleanup Script für PS5ImageConverter
- Entfernt Trailing Whitespace
- Bereinigt doppelte Leerzeilen (max. 2 aufeinanderfolgend)
- Warnt bei zu langen Zeilen
"""

import sys
import re

def cleanup_file(filepath):
    print(f"Bereinige: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_size = len(content)
    original_lines = content.count('\n')
    
    # 1. Entferne Trailing Whitespace
    lines = content.split('\n')
    lines = [line.rstrip() for line in lines]
    content = '\n'.join(lines)
    
    # 2. Ersetze 3+ aufeinanderfolgende Leerzeilen mit 2
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    # 3. Schreibe zurück
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    new_size = len(content)
    new_lines = content.count('\n')
    
    print(f"  Größe: {original_size:,} → {new_size:,} Bytes ({original_size - new_size} entfernt)")
    print(f"  Zeilen: {original_lines:,} → {new_lines:,} Zeilen ({original_lines - new_lines} entfernt)")
    
    # Warne vor langen Zeilen
    long_lines = []
    for i, line in enumerate(lines, 1):
        if len(line) > 120:
            long_lines.append((i, len(line)))
    
    if long_lines:
        print(f"\n  ⚠ {len(long_lines)} Zeilen > 120 Zeichen (nicht geändert, benötigen manuelle Überprüfung):")
        for line_num, length in long_lines[:5]:
            print(f"     - Zeile {line_num}: {length} Zeichen")
        if len(long_lines) > 5:
            print(f"     ... und {len(long_lines)-5} weitere")
    
    return True

if __name__ == '__main__':
    main_file = 'PS5ImageConverter_Pro_FINAL_revised.py'
    try:
        cleanup_file(main_file)
        print(f"\n✅ Cleanup abgeschlossen!")
    except Exception as e:
        print(f"❌ Fehler: {e}")
        sys.exit(1)
