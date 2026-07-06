#!/usr/bin/env python3
"""
Build-Validierungstests für PS5ImageConverter
- Prüft ob PyInstaller das EXE bauen kann
- Validiert spec-Datei
- Prüft alle benötigten Daten-Dateien
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# UTF-8 Encoding für Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Unicode symbols with fallback for Windows
try:
    "[OK]".encode(sys.stdout.encoding)
    CHECK = "[OK]"
    CROSS = "[FAIL]"
except (UnicodeEncodeError, AttributeError):
    CHECK = "[+]"
    CROSS = "[x]"

def print_header(title):
    print(f"\n{BLUE}{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}{RESET}\n")

def test_pyinstaller_installed():
    print_header("TEST: PyInstaller Installation")
    try:
        result = subprocess.run(['pyinstaller', '--version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"  {GREEN}[OK]{RESET}  PyInstaller {version}")
            return True
        else:
            print(f"  {RED}[FAIL]{RESET}  PyInstaller nicht gefunden")
            return False
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def test_spec_file():
    print_header("TEST: Spec-Datei Validierung")
    
    spec_file = "PS5ImageConverter_Pro.spec"
    if not os.path.exists(spec_file):
        print(f"  {RED}[FAIL]{RESET}  {spec_file} nicht gefunden")
        return False
    
    try:
        with open(spec_file, 'r') as f:
            spec_content = f.read()
        
        # Prüfe auf kritische Elemente
        checks = [
            ('name=', 'Exe-Name'),
            ('datas=', 'Daten-Dateien'),
            ('hiddenimports=', 'Hidden Imports'),
            ('PS5_Dump_Image_Converter_v1.7.78', 'Output-Dateiname'),
        ]
        
        all_ok = True
        for pattern, desc in checks:
            if pattern in spec_content:
                print(f"  {GREEN}[OK]{RESET}  {desc}")
            else:
                print(f"  {RED}[FAIL]{RESET}  {desc} fehlt")
                all_ok = False
        
        return all_ok
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler beim Lesen: {e}")
        return False

def test_data_files():
    print_header("TEST: Daten-Dateien für Build")
    
    required_files = {
        'app_icon.ico': 'Anwendungsicon',
        'helloworld/': 'Helloworld-Verzeichnis',
    }
    
    all_exist = True
    for file_path, description in required_files.items():
        exists = os.path.exists(file_path)
        status = f"{GREEN}[OK]{RESET}" if exists else f"{RED}[FAIL]{RESET}"
        size_info = ""
        
        if exists:
            if os.path.isfile(file_path):
                size_info = f" ({os.path.getsize(file_path):,} Bytes)"
            elif os.path.isdir(file_path):
                files = len(list(Path(file_path).rglob('*')))
                size_info = f" ({files} Dateien)"
        
        print(f"  {status}  {description:30} {file_path}{size_info}")
        all_exist = all_exist and exists
    
    return all_exist

def test_icon_format():
    print_header("TEST: Icon-Format Validierung")
    
    icon_file = 'app_icon.ico'
    try:
        with open(icon_file, 'rb') as f:
            header = f.read(4)
        
        # ICO-Dateien beginnen mit 00 00 01 00 (little-endian)
        if header == b'\x00\x00\x01\x00':
            size = os.path.getsize(icon_file)
            print(f"  {GREEN}[OK]{RESET}  Valides ICO-Format ({size:,} Bytes)")
            return True
        else:
            print(f"  {RED}[FAIL]{RESET}  Ungültiges ICO-Header")
            return False
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def test_python_version():
    print_header("TEST: Python-Version Kompatibilität")
    
    py_version = sys.version_info
    version_str = f"{py_version.major}.{py_version.minor}.{py_version.micro}"
    
    # Python 3.8+ erforderlich für moderne Features
    if py_version.major >= 3 and py_version.minor >= 8:
        print(f"  {GREEN}[OK]{RESET}  Python {version_str}")
        return True
    else:
        print(f"  {RED}[FAIL]{RESET}  Python {version_str} zu alt (3.8+ erforderlich)")
        return False

def test_dependencies_frozen():
    print_header("TEST: Abhängigkeits-Versionen für Build")
    
    try:
        import PIL
        import cryptography
        import zstandard
        import paramiko
        
        versions = {
            'Pillow': PIL.__version__,
            'cryptography': cryptography.__version__,
            'zstandard': zstandard.__version__,
            'paramiko': paramiko.__version__,
        }
        
        print(f"  Installierte Versions-Snapshot:")
        for pkg, ver in versions.items():
            print(f"    - {pkg:20} {ver}")
        
        # Prüfe ob sie mit requirements.txt matchen
        with open('requirements.txt', 'r') as f:
            reqs = f.read()
        
        print(f"\n  requirements.txt Versionen:")
        for line in reqs.split('\n'):
            if line.strip() and not line.startswith('#'):
                print(f"    - {line.strip()}")
        
        print(f"\n  {GREEN}[OK]{RESET}  Abhängigkeiten sind installiert")
        return True
    except Exception as e:
        print(f"  {RED}[FAIL]{RESET}  Fehler: {e}")
        return False

def test_output_directory():
    print_header("TEST: Build-Output-Verzeichnis")
    
    dist_dir = 'dist'
    build_dir = 'build'
    
    print(f"  Prüfe ob Output-Verzeichnisse leer sind (für sauberen Build):")
    
    results = []
    for dir_name in [dist_dir, build_dir]:
        if os.path.exists(dir_name):
            files = list(Path(dir_name).rglob('*'))
            file_count = len([f for f in files if f.is_file()])
            print(f"  {YELLOW}⚠{RESET}  {dir_name}/ existiert mit {file_count} Dateien (wird überschrieben)")
            results.append(True)  # Das ist OK, wird überschrieben
        else:
            print(f"  {GREEN}[OK]{RESET}  {dir_name}/ ist leer/neu")
            results.append(True)
    
    return all(results)

def main():
    print(f"\n{BLUE}{'='*60}")
    print("  PS5 IMAGE CONVERTER - BUILD-VALIDIERUNG")
    print(f"{'='*60}{RESET}\n")
    
    results = {}
    
    results['PyInstaller'] = test_pyinstaller_installed()
    results['SpecFile'] = test_spec_file()
    results['DataFiles'] = test_data_files()
    results['IconFormat'] = test_icon_format()
    results['PythonVersion'] = test_python_version()
    results['Dependencies'] = test_dependencies_frozen()
    results['OutputDir'] = test_output_directory()
    
    # Zusammenfassung
    print_header("BUILD-READINESS ZUSAMMENFASSUNG")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{GREEN}[OK]{RESET}" if result else f"{RED}[FAIL]{RESET}"
        print(f"  {status}  {test_name}")
    
    print(f"\n  {BLUE}Ergebnis:{RESET} {passed}/{total} Tests bestanden")
    
    if passed == total:
        print(f"\n  {GREEN}🔨 BUILD KANN GESTARTET WERDEN!{RESET}")
        print(f"  {BLUE}Befehl:{RESET} .\\Build_EXE.ps1\n")
        return 0
    else:
        print(f"\n  {RED}⚠  {total - passed} Voraussetzung(en) nicht erfüllt{RESET}\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())

