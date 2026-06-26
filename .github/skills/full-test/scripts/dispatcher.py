#!/usr/bin/env python3
"""
Full Test Suite Dispatcher
Orchestriert alle Test-Modi: vollständig, quick, hotfix
"""

import sys
import subprocess
from pathlib import Path

def get_test_script_path(script_name):
    """Gibt den Pfad zu einem Test-Script zurück"""
    # Dispatcher befindet sich in: .github/skills/full-test/scripts/
    # Test-Scripts befinden sich in: .github/skills/release-test/scripts/
    script_dir = Path(__file__).parent.parent.parent / "release-test" / "scripts"
    return script_dir / script_name

def run_test(script_name):
    """Führt ein Test-Script aus und gibt Exit Code zurück"""
    script_path = get_test_script_path(script_name)
    
    if not script_path.exists():
        print(f"ERROR: Test-Script nicht gefunden: {script_path}")
        return 1
    
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(script_path.parent.parent.parent.parent.parent)
        )
        return result.returncode
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

def main():
    """Main entry point für Skill"""
    
    # Bestimme welcher Test ausgeführt werden soll
    test_mode = sys.argv[1].lower() if len(sys.argv) > 1 else "full"
    
    if test_mode == "quick":
        print("Starting Quick Smoke Test (~15 Min)...\n")
        exit_code = run_test("quick_smoke_test.py")
    elif test_mode == "hotfix":
        print("Starting Hotfix Emergency Test (~5 Min)...\n")
        exit_code = run_test("hotfix_smoke_test.py")
    elif test_mode == "full" or test_mode == "":
        print("Starting Full Test Suite (~3 Min)...\n")
        exit_code = run_test("run_all_tests.py")
    else:
        print(f"Unknown test mode: {test_mode}")
        print("Usage: full-test [quick|hotfix|full]")
        print("  quick  - Quick Smoke Test (~15 Min)")
        print("  hotfix - Hotfix Emergency Test (~5 Min)")
        print("  full   - Full Test Suite (~3 Min) [default]")
        return 1
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
