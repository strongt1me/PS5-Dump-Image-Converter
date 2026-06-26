---
name: full-test
description: 'Full Test Suite - Vollständige automatisierte Validierung aller Komponenten. Nutze diese Skill für umfassende Code-Analyse, Syntax-Überprüfung, Build-Validierung und Quality-Checks.'
argument-hint: 'Optional: "quick" für Quick Smoke Test (~15 Min), "hotfix" für Hotfix Test (~5 Min), oder leer für vollständige Suite (~3 Min)'
user-invocable: true
---

# Full Test Suite Skill

Automatisierte vollständige Validierung aller Komponenten mit Syntax-Check, Build-Readiness und Quality-Suite.

## Wann verwenden

- **Vor jedem Release**: Komplette Validierung aller 8 Aufgaben und Module
- **Vor Commits/Merges**: Sicherstellen dass kein Code broken wird
- **Build-Validierung**: PyInstaller-Kompatibilität prüfen
- **Quality Gates**: Code-Standards und Best-Practices überprüfen
- **Kontinuierliche Integration**: Automatisierte Qualitätskontrolle

## Verfügbare Test-Modi

### 🔥 Vollständige Test Suite (Option 1) - Standard
```
/full-test
```
- **Dauer**: ~3 Minuten
- **Umfang**: Syntax + Build + Quality
- **Ideal für**: Vor Release, CI/CD Pipeline
- **Tests**:
  - Python Syntax-Überprüfung (py_compile)
  - Build-Readiness Validierung (PyInstaller, Abhängigkeiten, Icons)
  - Code-Quality Suite (Linting, Imports, Best-Practices)
- **Exit Code**: 0 = alle bestanden, 1 = Fehler

### ⚡ Quick Smoke Test - Fast Track
```
/full-test quick
```
- **Dauer**: ~15 Minuten
- **Fokus**: Startfähigkeit, Kernpfad, Validator
- **Ideal für**: Vor Upload, Schnelle Validierung
- **Tests**:
  - Syntax-Check
  - App-Start & UI-Responsiveness
  - Build-Readiness Checks
  - Quick Quality Checks

### 🚨 Hotfix Emergency Test - Notfall
```
/full-test hotfix
```
- **Dauer**: ~5 Minuten
- **Fokus**: 5 kritische Checks
- **Ideal für**: Zeitkritische Hotfixes
- **Tests**:
  - App Start
  - Moduswechsel
  - Syntax Check
  - Build-Readiness
- **Hinweis**: Danach 24h Quick-Smoke durchführen!

## Arbeitsablauf

### 1. Test-Initialisierung
- Projektstruktur überprüfen
- Python-Umgebung validieren
- Test-Dateien prüfen

### 2. Syntax-Überprüfung
- Python-Syntax mit py_compile prüfen
- Hauptdatei kompilieren
- Import-Validierung

### 3. Build-Readiness Tests
- PyInstaller Installation überprüfen
- Spec-Datei validieren
- Icon-Dateien prüfen
- Datenfiles verifizieren
- Python-Version Kompatibilität
- Abhängigkeits-Versionen

### 4. Code-Quality Suite
- Syntax-Fehler erkennen
- Unused Imports finden
- Code-Standards überprüfen
- Best-Practices validieren
- Linting durchführen

### 5. Ergebnis & Entscheidung
- Alle Tests zusammengefasst
- Exit Code zeigt Erfolg/Fehler
- GO/NO-GO für Release

## Durchführung

### Via Skill-Befehl

**Vollständige Test Suite:**
```bash
/full-test
```

**Quick Smoke Test:**
```bash
/full-test quick
```

**Hotfix Emergency:**
```bash
/full-test hotfix
```

### Via Kommandozeile

**Vollständige Suite:**
```bash
python .github/skills/release-test/scripts/run_all_tests.py
```

**Quick Smoke:**
```bash
python .github/skills/release-test/scripts/quick_smoke_test.py
```

**Hotfix:**
```bash
python .github/skills/release-test/scripts/hotfix_smoke_test.py
```

## Release-Entscheidungsmatrix

| Szenario | Test | Exit Code | Entscheidung |
|----------|------|-----------|--------------|
| Standard Release | `run_all_tests.py` | 0 = SUCCESS | → GO für Build/Release |
| Vor Upload | `quick_smoke_test.py` | 0 = SUCCESS | → GO für Release-Upload |
| Kritischer Hotfix | `hotfix_smoke_test.py` | 0 = SUCCESS | → GO, danach 24h Quick-Smoke |
| Beliebiger Test | beliebig | 1 = FAILURE | → Fehler debuggen, Korrektionen |

## Test-Ausgabe-Interpretation

### SUCCESS (Exit Code 0)
```
✓ ALLE TESTS BESTANDEN - GO FÜR RELEASE!
```
- Alle Komponenten funktionieren
- Code-Qualität OK
- Build kann erfolgen

### FAILURE (Exit Code 1)
```
✗ Test-Kategorien fehlgeschlagen:
   - Syntax-Check
   - Build-Readiness
   - Quality-Suite
```
- Fehler müssen behoben werden
- Hinweise in der Ausgabe beachten
- Tests wiederholen nach Fixes

## Best Practices

### Vor jedem Commit
```bash
python .github/skills/release-test/scripts/quick_smoke_test.py
```

### Vor jedem Release
```bash
python .github/skills/release-test/scripts/run_all_tests.py
```

### Bei Hotfixes
```bash
python .github/skills/release-test/scripts/hotfix_smoke_test.py
# Danach innerhalb 24h:
python .github/skills/release-test/scripts/quick_smoke_test.py
```

### CI/CD Pipeline
```yaml
- name: Full Test Suite
  run: python .github/skills/release-test/scripts/run_all_tests.py
```

## Fehlerbehandlung

### Encoding-Fehler (Windows PowerShell)
Wenn Unicode-Fehler erscheinen, ist das normal. Die Test-Scripts verwenden für Windows-Kompatibilität ASCII-Symbole ([OK], [FAIL]).

### Pfad-Fehler
Falls Test-Dateien nicht gefunden werden:
- Überprüfe dass die Scripts im korrekten Verzeichnis existieren
- Prüfe `.github/skills/release-test/scripts/` Verzeichnis
- Stelle sicher dass aus dem Projektroot ausgeführt wird

### PyInstaller-Fehler
Wenn PyInstaller-Installation fehlschlägt:
```bash
pip install pyinstaller
```

## Script-Details

- **run_all_tests.py**: Master-Script, führt alle Tests sequenziell aus
- **quick_smoke_test.py**: Fast-Track Validierung (15 Min)
- **hotfix_smoke_test.py**: Emergency Validierung (5 Min)

Siehe [Test Scripts Referenz](../release-test/references/test_scripts_reference.md) für technische Details.
