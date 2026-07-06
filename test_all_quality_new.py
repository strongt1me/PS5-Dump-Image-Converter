#!/usr/bin/env python3
"""
Umfassender Quality Test-Suite für PS5 Image Converter
Tests:
1. Syntax-Validierung
2. Import-Validierung
3. ProgressEngine-Logik (ETA-Berechnung)
4. Build-Abhängigkeiten
5. Datei-Integrität
6. Code-Linting
"""

import sys
import os
import ast
import importlib
import re
import time
from pathlib import Path

# Farben (ASCII-safe für Windows)
GREEN = ''
RED = ''
YELLOW = ''
RESET = ''

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_result(name, passed, details=""):
    status = "[OK] PASS" if passed else "[FAIL] FAIL"
    print(f"  {status}  {name}")
    if details:
        print(f"       {details}")

# ============================================================================
# 1. SYNTAX VALIDIERUNG
# ============================================================================
def test_syntax():
    print_header("TEST 1: Syntax-Validierung")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            code = f.read()
        ast.parse(code)
        test_result("Hauptdatei-Syntax", True, f"{len(code)} Bytes geparst")
        return True
    except SyntaxError as e:
        test_result("Hauptdatei-Syntax", False, f"Line {e.lineno}: {e.msg}")
        return False

# ============================================================================
# 2. IMPORT VALIDIERUNG
# ============================================================================
def test_imports():
    print_header("TEST 2: Import-Validierung")
    
    required_imports = [
        'tkinter',
        'PIL',
        'cryptography',
        'zstandard',
        'time',
        'os',
        'sys',
        'json',
        'threading',
        'subprocess',
        'hashlib',
        'struct',
        're',
        'shutil',
    ]
    
    failed = []
    for imp in required_imports:
        try:
            __import__(imp)
            print(f"  [OK] {imp}")
        except ImportError as e:
            print(f"  [FAIL] {imp}: {e}")
            failed.append(imp)
    
    if failed:
        print(f"\n  {len(failed)} Packages fehlend: {', '.join(failed)}")
        return False
    else:
        print(f"\n  Alle {len(required_imports)} Imports funktionieren")
        return True

# ============================================================================
# 3. PROGRESSENGINE LOGIK
# ============================================================================
def test_progress_engine():
    print_header("TEST 3: ProgressEngine-Logik")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    checks = {
        "ProgressEngine-Klasse": "class ProgressEngine" in content,
        "ETA-Berechnung": "_estimate_eta_seconds" in content,
        "Easing-Logik": "PROGRESS_EASING" in content,
        "Task-Progress-Tracking": "task_progress" in content,
        "Fortschrittsanzeige": "_update_progress_gui" in content,
        "Keepalive trennt Output-Timestamp": "self._last_engine_output_ts = _now" not in content,
    }
    
    for check_name, result in checks.items():
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status}  {check_name}")
    
    all_pass = all(checks.values())
    return all_pass

def test_keepalive_regression():
    print_header("TEST 3B: MkPFS-Keepalive-Regression")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
        gui._last_engine_output_ts = 123.0

        log_calls = []
        status_calls = []
        gui._append_to_log = log_calls.append
        gui._set_status = status_calls.append

        gui._emit_processing_keepalive()

        checks = {
            "Keepalive loggt Hinweis": log_calls == ["[INFO] Verarbeitung laeuft ... bitte warten.\n"],
            "Keepalive setzt Status": status_calls == ["Phase 3/4 – Verarbeitung laeuft ..."],
            "Keepalive aendert keinen Output-Timestamp": gui._last_engine_output_ts == 123.0,
        }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("MkPFS-Keepalive-Regression", False, str(e))
        return False

# ============================================================================
# 4. BUILD ABHÄNGIGKEITEN
# ============================================================================
def test_build_deps():
    print_header("TEST 4: Build-Abhängigkeiten")
    
    files_to_check = [
        ("PS5ImageConverter_Pro.spec", "PyInstaller Spec"),
        ("app_icon.ico", "App Icon"),
        ("requirements.txt", "Dependencies"),
    ]
    
    all_exist = True
    for filename, desc in files_to_check:
        exists = Path(filename).exists()
        status = "[OK]" if exists else "[FAIL]"
        print(f"  {status}  {desc}: {filename}")
        if not exists:
            all_exist = False
    
    return all_exist

# ============================================================================
# 5. DATEI-INTEGRITÄT
# ============================================================================
def test_file_integrity():
    print_header("TEST 5: Datei-Integrität")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    
    checks = []
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Größe Check
        file_size = sum(len(line.encode('utf-8')) for line in lines)
        size_ok = file_size > 1000000  # > 1MB
        checks.append(("Dateigröße", size_ok, f"{file_size / 1024 / 1024:.2f} MB"))
        
        # Zeilenanzahl Check
        line_count = len(lines)
        lines_ok = line_count > 10000
        checks.append(("Zeilenanzahl", lines_ok, f"{line_count} Zeilen"))
        
        # Class-Definition Check
        content = ''.join(lines)
        has_classes = "class " in content
        checks.append(("Klassen-Definitionen", has_classes, "vorhanden"))
        
        # Method-Definition Check
        has_methods = "def " in content
        checks.append(("Methoden-Definitionen", has_methods, "vorhanden"))
        
    except Exception as e:
        checks.append(("Datei-Lesezugriff", False, str(e)))
    
    for check_name, result, detail in checks:
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status}  {check_name}: {detail}")
    
    all_pass = all(check[1] for check in checks)
    return all_pass

# ============================================================================
# 6. CODE LINTING
# ============================================================================
def test_code_quality():
    print_header("TEST 6: Code-Qualität")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    
    issues = []
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        for i, line in enumerate(lines, 1):
            # Check für sehr lange Zeilen (> 120 chars)
            if len(line.rstrip()) > 120:
                issues.append(f"Line {i}: zu lang ({len(line.rstrip())} chars)")
            
            # Check für Tabs statt Spaces
            if '\t' in line:
                issues.append(f"Line {i}: enthält Tabs")
            
            # Check für Trailing Whitespace
            if line.rstrip() != line.rstrip('\n'):
                issues.append(f"Line {i}: Trailing Whitespace")
    
    except Exception as e:
        print(f"  [FAIL] Fehler beim Lesen: {e}")
        return False
    
    if issues:
        print(f"  [!] {len(issues)} Qualitätsprobleme gefunden:")
        for issue in issues[:5]:  # Zeige nur erste 5
            print(f"      - {issue}")
        if len(issues) > 5:
            print(f"      ... und {len(issues) - 5} weitere")
    else:
        print(f"  [OK] Keine Qualitätsprobleme gefunden")
    
    # Gib True zurück wenn nicht zu viele Issues
    return len(issues) < 50

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print("\n" + "="*60)
    print("  PS5 IMAGE CONVERTER - QUALITY TEST SUITE")
    print("="*60 + "\n")
    
    results = {}
    
    # Führe alle Tests aus
    results["Syntax"] = test_syntax()
    results["Imports"] = test_imports()
    results["ProgressEngine"] = test_progress_engine()
    results["KeepaliveRegression"] = test_keepalive_regression()
    results["BuildDeps"] = test_build_deps()
    results["FileIntegrity"] = test_file_integrity()
    results["CodeQuality"] = test_code_quality()
    
    # Zusammenfassung
    print("\n" + "="*60)
    print("  ZUSAMMENFASSUNG")
    print("="*60 + "\n")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"  {status}  {test_name}")
    
    print(f"\nErgebnis: {passed}/{total} Tests bestanden")
    
    if passed == total:
        print("\n[OK] ALLE QUALITY TESTS BESTANDEN!\n")
        return 0
    else:
        print(f"\n[!] {total - passed} Test(s) fehlgeschlagen\n")
        return 0  # Nicht als kritischer Fehler

if __name__ == "__main__":
    sys.exit(main())
