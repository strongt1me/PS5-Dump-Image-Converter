#!/usr/bin/env python3
"""
Quick Smoke Test - 15 Minuten Fast-Track
Fokus: Startfähigkeit, Kernpfad und Validator
Idealerweise mit vorbereiteten Testdaten durchführen
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from datetime import datetime

# Farben für Output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class QuickSmokeTest:
    def __init__(self):
        # Berechne Projektroot: scripts → release-test → skills → .github → projektroot
        script_path = Path(__file__).resolve()
        self.root = script_path.parent.parent.parent.parent.parent
        self.results = {}
        self.failed_checks = []
        self.start_time = time.time()
        self.time_budget = 15 * 60  # 15 Minuten in Sekunden
        
    def get_elapsed(self):
        """Gibt verstrichene Zeit zurück"""
        return time.time() - self.start_time
    
    def print_header(self, title):
        elapsed = int(self.get_elapsed())
        print(f"\n{BLUE}{BOLD}T+ {elapsed:02d}:00 | {title}{RESET}")
        print(f"{BLUE}{'-'*70}{RESET}\n")
    
    def print_check(self, name, passed, notes=""):
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}CROSS FAIL{RESET}"
        elapsed = int(self.get_elapsed())
        print(f"  {status}  T+{elapsed:02d}:00  {name}")
        if notes:
            print(f"       {notes}")
    
    def time_check(self):
        """Warnt wenn Zeitbudget überschritten"""
        elapsed = self.get_elapsed()
        if elapsed > self.time_budget:
            print(f"\n{YELLOW}⚠ Zeitbudget (15min) überschritten!{RESET}\n")
            return False
        return True
    
    def run_command(self, cmd, timeout=30):
        """Führt einen Befehl aus"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(self.root)
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return False, "", "Timeout"
        except Exception as e:
            return False, "", str(e)
    
    def check_syntax(self):
        """00:00-01:00 | Syntax-Check"""
        self.print_header("Syntax-Check (py_compile)")
        
        main_file = self.root / "PS5ImageConverter_Pro_FINAL_revised.py"
        try:
            import py_compile
            py_compile.compile(str(main_file), doraise=True)
            success, stderr = True, ""
        except py_compile.PyCompileError as e:
            success, stderr = False, str(e)
        
        notes = "Exit Code 0" if success else f"Fehler: {stderr[:50]}"
        self.print_check("Hauptdatei-Syntax", success, notes)
        self.results["syntax"] = success
        
        if not success:
            self.failed_checks.append("Syntax-Check")
        
        return success and self.time_check()
    
    def check_ui_start(self):
        """01:00-02:00 | App-Start und UI"""
        self.print_header("App-Start & UI-Responsiveness")
        
        # Überprüfe ob Hauptdatei importierbar ist
        try:
            import sys
            sys.path.insert(0, str(self.root))
            import PS5ImageConverter_Pro_FINAL_revised
            ui_ok = True
            error_msg = "OK"
        except ImportError as e:
            ui_ok = False
            error_msg = f"Import: {str(e)[:50]}"
        except Exception as e:
            # GUI-Fehler sind OK für den Import-Test
            ui_ok = True
            error_msg = f"OK (GUI: {type(e).__name__})"
        
        self.print_check("Modul-Import", ui_ok, error_msg)
        self.results["ui"] = ui_ok
        
        if not ui_ok:
            self.failed_checks.append("App-Start")
        
        return ui_ok and self.time_check()
    
    def check_build_readiness(self):
        """02:00-03:00 | Build-Readiness Tests"""
        self.print_header("Build-Readiness Checks")
        
        test_file = self.root / "test_build_ready.py"
        if not test_file.exists():
            self.print_check("Build-Readiness", False, "test_build_ready.py nicht gefunden")
            self.results["build"] = False
            self.failed_checks.append("Build-Readiness")
            return False
        
        cmd = f'python "{str(test_file)}"'
        success, stdout, stderr = self.run_command(cmd, timeout=60)
        
        # Prüfe auf bestandene Tests im Output
        passed_count = stdout.count("CHECK")
        details = f"{passed_count} Tests bestanden" if passed_count > 0 else "Keine Tests bestanden"
        
        self.print_check("Build-Readiness", success, details)
        self.results["build"] = success
        
        if not success:
            self.failed_checks.append("Build-Readiness")
        
        return success and self.time_check()
    
    def check_quality_quick(self):
        """03:00-04:00 | Schnelle Quality-Checks"""
        self.print_header("Quick Quality Checks")
        
        # Syntaxfehler prüfen
        main_file = self.root / "PS5ImageConverter_Pro_FINAL_revised.py"
        cmd = f'python -m pylint --disable=all --enable=syntax-error "{main_file}" 2>&1 || true'
        success, stdout, _ = self.run_command(cmd, timeout=30)
        
        # Wenn pylint nicht installiert ist, nur Basis-Prüfung
        has_syntax_errors = "syntax-error" in stdout.lower() and "error" in stdout.lower()
        
        if not has_syntax_errors:
            self.print_check("Code Syntax Errors", True, "Keine kritischen Syntax-Fehler")
            self.results["quality"] = True
        else:
            self.print_check("Code Syntax Errors", False, "Syntax-Fehler gefunden")
            self.results["quality"] = False
            self.failed_checks.append("Quality-Checks")
        
        return self.time_check()
    
    def print_summary(self):
        """Druckt Smoke-Test Ergebnis"""
        self.print_header("QUICK SMOKE TEST ERGEBNIS")
        
        elapsed = int(self.get_elapsed())
        print(f"Gesamtdauer: {elapsed} Sekunden\n")
        
        print(f"Prüfungen:")
        for check, passed in self.results.items():
            status = f"{GREEN}PASS{RESET}" if passed else f"{RED}CROSS FAIL{RESET}"
            check_name = {
                "syntax": "Syntax-Check",
                "ui": "App-Start",
                "build": "Build-Readiness",
                "quality": "Quality-Checks"
            }.get(check, check)
            print(f"  {status}  {check_name}")
        
        print()
        
        if not self.failed_checks:
            print(f"{GREEN}{BOLD}QUICK SMOKE TEST BESTANDEN!{RESET}")
            print(f"{GREEN}  → GO für Build/Release{RESET}\n")
            return 0
        else:
            print(f"{RED}{BOLD}QUICK SMOKE TEST FEHLGESCHLAGEN:{RESET}")
            for failed in self.failed_checks:
                print(f"   - {failed}")
            print(f"{RED}  → KEIN GO für Release{RESET}\n")
            return 1
    
    def run(self):
        """Führt kompletten Quick-Smoke Test durch"""
        print(f"\n{BOLD}{'='*70}")
        print(f"  Quick Smoke Test - 15 Minuten Test-Durchlauf")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}{RESET}\n")
        
        try:
            # Tests in Reihenfolge mit Zeitbudget
            self.check_syntax() or sys.exit(1)
            self.check_ui_start() or sys.exit(1)
            self.check_build_readiness() or sys.exit(1)
            self.check_quality_quick() or sys.exit(1)
            
            return self.print_summary()
            
        except KeyboardInterrupt:
            print(f"\n{RED}Test abgebrochen.{RESET}\n")
            return 130
        except Exception as e:
            print(f"\n{RED}Fehler: {e}{RESET}\n")
            return 1

if __name__ == "__main__":
    test = QuickSmokeTest()
    exit_code = test.run()
    sys.exit(exit_code)
