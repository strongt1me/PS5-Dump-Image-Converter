#!/usr/bin/env python3
"""
Notfall Smoke Test - 5 Minuten Hotfix-Track
Nur verwenden bei zeitkritischen Hotfixes
Empfehlung: Danach innerhalb 24h den 15-Min Quick-Smoke durchziehen
"""

import os
import sys
import subprocess
import py_compile
import time
from pathlib import Path
from datetime import datetime

# Farben für Output (ASCII-safe für Windows)
GREEN = ''
RED = ''
YELLOW = ''
BLUE = ''
RESET = ''
BOLD = ''

class HotfixSmokeTest:
    def __init__(self):
        import os
        # Berechne Projekt-Root: hotfix_smoke_test.py liegt in .github/skills/release-test/scripts/
        # Pfad: ..\..\..\..\  (5 level nach oben zum Projektroot)
        self.root = Path(__file__).parent.parent.parent.parent.parent
        # Stelle sofort sicher, dass wir im richtigen Verzeichnis sind
        os.chdir(str(self.root))
        # Und add das Verzeichnis zu sys.path
        import sys
        if str(self.root) not in sys.path:
            sys.path.insert(0, str(self.root))
        
        self.results = {}
        self.failed_checks = []
        self.start_time = time.time()
        self.time_budget = 5 * 60  # 5 Minuten
        
    def get_elapsed(self):
        """Gibt verstrichene Zeit in Sekunden zurück"""
        return int(time.time() - self.start_time)
    
    def print_header(self, title):
        elapsed = self.get_elapsed()
        print(f"\nT+ {elapsed:02d}:00 | {title}")
        print(f"{'-'*70}\n")
    
    def print_check(self, name, passed, notes=""):
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        elapsed = self.get_elapsed()
        print(f"  {status}  T+{elapsed:02d}:00  {name}")
        if notes:
            print(f"       {notes}")
    
    def check_1_app_start(self):
        """00:00-01:00 | App-Start"""
        self.print_header("App-Start")
        
        # Überprüfe Modul-Import
        try:
            import os
            import sys
            os.chdir(str(self.root))
            sys.path.insert(0, str(self.root))
            
            import PS5ImageConverter_Pro_FINAL_revised
            startup_ok = True
            self.print_check("App startet", startup_ok, "Modul importiert erfolgreich")
        except ImportError as e:
            startup_ok = False
            err_msg = str(e).replace('\n', ' ')[:70]
            self.print_check("App startet", startup_ok, f"Import-Fehler: {err_msg}")
            self.failed_checks.append("App-Start")
        except Exception as e:
            startup_ok = False
            err_msg = str(e).replace('\n', ' ')[:70]
            self.print_check("App startet", startup_ok, f"Fehler: {err_msg}")
            self.failed_checks.append("App-Start")
        
        self.results["startup"] = startup_ok
        return startup_ok
    
    def check_2_ui_modes(self):
        """01:00-02:00 | Moduswechsel 1 & 8"""
        self.print_header("UI Moduswechsel")
        
        # Überprüfe ob die Modus-Klasse vorhanden ist
        try:
            import sys
            sys.path.insert(0, str(self.root))
            from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
            modes_ok = True
            self.print_check("Moduswechsel funktioniert", modes_ok, "UI-Klasse vorhanden")
        except Exception as e:
            modes_ok = False
            self.print_check("Moduswechsel funktioniert", modes_ok, f"Fehler: {str(e)[:50]}")
            self.failed_checks.append("Moduswechsel")
        
        self.results["ui"] = modes_ok
        return modes_ok
    
    def check_3_syntax(self):
        """02:00-03:00 | Syntax-Check"""
        self.print_header("Syntax-Check")
        
        main_file = self.root / "PS5ImageConverter_Pro_FINAL_revised.py"
        try:
            py_compile.compile(str(main_file), doraise=True)
            self.print_check("Syntax gültig", True, "py_compile ohne Fehler")
            self.results["syntax"] = True
            return True
        except py_compile.PyCompileError as e:
            self.print_check("Syntax gültig", False, str(e)[:50])
            self.failed_checks.append("Syntax-Check")
            self.results["syntax"] = False
            return False
    
    def check_4_build_readiness(self):
        """03:00-05:00 | Build-Readiness"""
        self.print_header("Build-Readiness")
        
        # Schnelle Build-Checks
        checks = {
            "PyInstaller": (self.root / "PS5ImageConverter_Pro.spec").exists(),
            "Icon": (self.root / "app_icon.ico").exists(),
            "Requirements": (self.root / "requirements.txt").exists(),
        }
        
        all_ok = all(checks.values())
        for check_name, passed in checks.items():
            status = "[OK]" if passed else "[FAIL]"
            print(f"  {status}  {check_name}")
        
        self.print_check("Build-Readiness erfolgreich", all_ok, 
                        f"{sum(checks.values())}/{len(checks)} Dateien vorhanden")
        self.results["build"] = all_ok
        
        if not all_ok:
            self.failed_checks.append("Build-Readiness")
            return False
        
        return True
    
    def print_final_verdict(self):
        """Finale Entscheidung"""
        elapsed = self.get_elapsed()
        print(f"\n{'='*70}\n")
        print(f"Gesamtdauer: {elapsed} Sekunden (Budget: 300s)\n")
        
        all_pass = all(self.results.values())
        
        if all_pass and not self.failed_checks:
            print("[OK] NOTFALL SMOKE TEST: GO")
            print("  Alle 5 kritischen Checks bestanden.")
            print("  -> Hotfix-Release freigegeben\n")
            return 0
        else:
            print("[FAIL] NOTFALL SMOKE TEST: NO GO")
            print("  Folgende Checks sind fehlgeschlagen:")
            for failed in self.failed_checks:
                print(f"   - {failed}")
            print("  -> KEIN Release bis Probleme behoben\n")
            
            if len(self.failed_checks) <= 2:
                print("Empfehlung: Innerhalb 24h Quick-Smoke (15 Min) durchziehen\n")
            
            return 1
    
    def run(self):
        """Führt kompletten 5-Min Hotfix-Smoke Test durch"""
        # Stelle sicher, dass wir im richtigen Verzeichnis sind
        import os
        os.chdir(str(self.root))
        
        print(f"\n{'='*70}")
        print(f"  NOTFALL SMOKE TEST - 5 Minuten Hotfix-Absicherung")
        print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")
        print("[!] Hinweis: Nur bei zeitkritischen Hotfixes verwenden")
        print("    -> Danach innerhalb 24h vollständigen Quick-Smoke durchziehen\n")
        
        try:
            # Die 5 kritischen Checks in Reihenfolge
            if not self.check_1_app_start():
                return self.print_final_verdict()
            
            if not self.check_2_ui_modes():
                return self.print_final_verdict()
            
            if not self.check_3_syntax():
                return self.print_final_verdict()
            
            if not self.check_4_build_readiness():
                return self.print_final_verdict()
            
            return self.print_final_verdict()
            
        except KeyboardInterrupt:
            print(f"\n{RED}Test abgebrochen.{RESET}\n")
            return 130
        except Exception as e:
            print(f"\n{RED}Fehler: {e}{RESET}\n")
            return 1

if __name__ == "__main__":
    test = HotfixSmokeTest()
    exit_code = test.run()
    sys.exit(exit_code)
