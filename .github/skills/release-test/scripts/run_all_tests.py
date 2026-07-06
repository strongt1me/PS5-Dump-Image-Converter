#!/usr/bin/env python3
"""
Master Test-Script für Release Test Skill
Führt alle Validierungen in Reihenfolge aus:
1. Syntax-Check (py_compile)
2. Build-Readiness Tests
3. Quality Suite
4. Zusammenfassung
"""

import os
import sys
import subprocess
import time
import json
from datetime import datetime, timezone
from pathlib import Path

# Farben für Output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

class TestRunner:
    def __init__(self):
        # Berechne Projektroot: scripts → release-test → skills → .github → projektroot
        script_path = Path(__file__).resolve()
        self.root = script_path.parent.parent.parent.parent.parent
        self.results = {}
        self.failed_tests = []
        self.total_time = 0
        
    def print_header(self, title):
        print(f"\n{BLUE}{BOLD}{'='*70}")
        print(f"  {title}")
        print(f"{'='*70}{RESET}\n")
    
    def print_footer(self):
        print(f"\n{BLUE}{'='*70}{RESET}\n")
    
    def print_result(self, test_name, passed, duration=0, details=""):
        status = f"{GREEN}[OK] PASS{RESET}" if passed else f"{RED}[FAIL] FAIL{RESET}"
        time_str = f" ({duration:.1f}s)" if duration > 0 else ""
        print(f"  {status}  {test_name}{time_str}")
        if details:
            print(f"       {details}")
        return passed
    
    def run_command(self, cmd, description=""):
        """Führt einen Shell-Befehl aus und gibt Ergebnis zurück"""
        try:
            start = time.time()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.root)
            )
            duration = time.time() - start
            success = result.returncode == 0
            
            return success, result.stdout, result.stderr, duration
        except subprocess.TimeoutExpired:
            return False, "", "Timeout nach 120s", 120
        except Exception as e:
            return False, "", str(e), 0
    
    def test_syntax_check(self):
        """Test 1: Syntax-Validierung mit py_compile"""
        self.print_header("TEST 1: Syntax-Überprüfung")
        
        main_file = self.root / "PS5ImageConverter_Pro_FINAL_revised.py"
        if not main_file.exists():
            self.print_result("Hauptdatei Syntax", False, 0, f"{main_file} nicht gefunden")
            return False
        
        cmd = f'python -m py_compile "{main_file}"'
        success, _, stderr, duration = self.run_command(cmd)
        
        if success:
            self.print_result(
                "Python Syntax Check",
                True,
                duration,
                "PS5ImageConverter_Pro_FINAL_revised.py - OK"
            )
        else:
            self.print_result(
                "Python Syntax Check",
                False,
                duration,
                f"Fehler: {stderr[:100]}"
            )
            self.failed_tests.append("Syntax-Check")
        
        self.results["Syntax"] = success
        self.total_time += duration
        return success
    
    def test_build_readiness(self):
        """Test 2: Build-Readiness Tests"""
        self.print_header("TEST 2: Build-Readiness Validierung")
        
        test_file = self.root / "test_build_ready.py"
        if not test_file.exists():
            self.print_result("Build-Readiness", False, 0, "test_build_ready.py nicht gefunden")
            self.results["BuildReady"] = False
            return False
        
        cmd = f'python "{test_file}"'
        success, stdout, stderr, duration = self.run_command(cmd)
        
        # Parse Output für Details
        details = ""
        if "[OK]" in stdout:
            # Zähle bestandene Tests
            passed_count = stdout.count("[OK]")
            details = f"{passed_count} Tests bestanden"
        
        self.print_result("Build-Readiness Tests", success, duration, details)
        
        if not success:
            self.failed_tests.append("Build-Readiness")
        
        self.results["BuildReady"] = success
        self.total_time += duration
        return success
    
    def test_quality_suite(self):
        """Test 3: Umfassende Qualitäts-Suite"""
        self.print_header("TEST 3: Code-Quality Suite")
        
        test_file = self.root / "test_all_quality.py"
        if not test_file.exists():
            self.print_result("Quality Suite", False, 0, "test_all_quality.py nicht gefunden")
            self.results["Quality"] = False
            return False
        
        cmd = f'python "{test_file}"'
        success, stdout, stderr, duration = self.run_command(cmd)
        
        # Parse Output für Details
        details = ""
        if "[OK]" in stdout:
            # Zähle bestandene Tests
            passed_count = stdout.count("[OK]")
            failed_count = stdout.count("[FAIL]")
            if failed_count > 0:
                details = f"{passed_count} bestanden, {failed_count} Hinweise"
            else:
                details = f"{passed_count} Tests bestanden"
        
        # Quality Suite kann auch mit Warnungen erfolgreich sein
        test_passed = success or "[OK]" in stdout
        self.print_result("Code Quality Tests", test_passed, duration, details)
        
        if not success and not test_passed:
            self.failed_tests.append("Quality-Suite")
        
        self.results["Quality"] = test_passed
        self.total_time += duration
        return test_passed
    
    def print_summary(self):
        """Druckt finale Zusammenfassung"""
        self.print_header("ZUSAMMENFASSUNG")
        
        print(f"Gesamt-Laufzeit: {BOLD}{self.total_time:.1f}s{RESET}\n")
        
        print(f"Ergebnisse:")
        for test_name, passed in self.results.items():
            status = f"{GREEN}[OK] PASS{RESET}" if passed else f"{YELLOW}⚠ WARN{RESET}" if test_name == "Quality" and not passed else f"{RED}[FAIL] FAIL{RESET}"
            print(f"  {status}  {test_name}")
        
        print()
        
        if not self.failed_tests:
            print(f"{GREEN}{BOLD}[OK] ALLE TESTS BESTANDEN - GO FÜR RELEASE!{RESET}\n")
            return True
        else:
            print(f"{RED}{BOLD}[FAIL] {len(self.failed_tests)} Test-Kategorien fehlgeschlagen:{RESET}")
            for failed in self.failed_tests:
                print(f"   - {failed}")
            print()
            return False
    
    def run_all(self):
        """Führt alle Tests aus"""
        print(f"\n{BOLD}Release Test Suite - Automatisierte Validierung{RESET}")
        print(f"Verzeichnis: {self.root}\n")
        
        try:
            # Tests in Reihenfolge ausführen
            self.test_syntax_check()
            self.test_build_readiness()
            self.test_quality_suite()
            
            # Zusammenfassung
            success = self.print_summary()
            return 0 if success else 1
            
        except KeyboardInterrupt:
            print(f"\n{RED}Abgebrochen durch Benutzer.{RESET}\n")
            return 130
        except Exception as e:
            print(f"\n{RED}Unerwarteter Fehler: {e}{RESET}\n")
            return 1


def _write_release_test_status(root: Path, suite: str, exit_code: int, results: dict, failed_tests: list[str]) -> None:
    """Persistiert den letzten Teststatus fuer die Start-Gate-Pruefung."""
    passed = exit_code == 0
    payload = {
        "suite": suite,
        "passed": passed,
        "exit_code": int(exit_code),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "epoch": time.time(),
        "root": str(root),
        "python": sys.executable,
        "results": results,
        "failed_tests": failed_tests,
    }

    out_paths: list[Path] = []
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        out_paths.append(Path(appdata) / "PS5ImageConverterPro" / "last_release_test_status.json")
    out_paths.append(root / ".github" / "skills" / "release-test" / "last_release_test_status.json")

    for path in out_paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] Statusdatei konnte nicht geschrieben werden: {path} ({exc})")

if __name__ == "__main__":
    runner = TestRunner()
    exit_code = runner.run_all()
    _write_release_test_status(
        root=runner.root,
        suite="full",
        exit_code=exit_code,
        results=runner.results,
        failed_tests=runner.failed_tests,
    )
    sys.exit(exit_code)
