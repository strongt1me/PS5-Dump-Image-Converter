#!/usr/bin/env python3
"""
Repariere test_all_quality.py - stelle saubere Version her
"""

# Der ursprüngliche Anfang ohne meine fehlerhaften Replacements
original_start = """#!/usr/bin/env python3
\"\"\"
Umfassender Test-Suite für PS5 Image Converter
Tests:
1. Syntax-Validierung
2. Import-Validierung
3. ProgressEngine-Logik (ETA-Berechnung)
4. Build-Abhängigkeiten
5. Datei-Integrität
6. Code-Linting
\"\"\"

import sys
import os
import ast
import re
import time
from pathlib import Path

# Farben für Output
GREEN = '\\033[92m'
RED = '\\033[91m'
YELLOW = '\\033[93m'
BLUE = '\\033[94m'
RESET = '\\033[0m'

def print_header(title):
    print(f"\\n{BLUE}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{RESET}\\n")

def test_result(name, passed, details=""):
    status = f"{GREEN}[OK] PASS{RESET}" if passed else f"{RED}[FAIL] FAIL{RESET}"
    print(f"  {status}  {name}")
    if details:
        print(f"       {details}")
"""

print("Repariere test_all_quality.py...")
print("Schreibe saubere Startzeilen...")

# Lese die aktuelle kaputte Datei
with open('test_all_quality.py', 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Ersetze den kaputten Anfang durch den Original-Anfang
if 'YE[-]' in content or '[-]mage' in content:
    # Finde wo der echte Content anfängt (nach den Definitionen)
    import_idx = content.find('def print_header')
    if import_idx < 0:
        import_idx = content.find('def test_result')
    
    if import_idx > 0:
        # Nimm alles nach den Definitionen
        rest = content[import_idx:]
        # Behalte nur den funktionalen Code
        content = original_start + rest
    else:
        print("ERROR: Kann das kaputte Format nicht reparieren")
        sys.exit(1)

# Ersetze alle Unicode-Symbole durch ASCII-Text
content = content.replace('✓', '[OK]')
content = content.replace('✗', '[FAIL]')
content = content.replace('⚠', '[!]')

with open('test_all_quality.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("[OK] test_all_quality.py repariert!")
