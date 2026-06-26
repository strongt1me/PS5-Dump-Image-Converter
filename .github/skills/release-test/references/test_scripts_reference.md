# Test Scripts - Referenzdokumentation

Automatisierte Test-Scripts für verschiedene Release-Szenarien und Zeitbudgets.

## Übersicht

| Script | Dauer | Zweck | Startbefehl |
|--------|-------|-------|-------------|
| [run_all_tests.py](../scripts/run_all_tests.py) | ~3 Min | Vollständige Validierung | `python ./run_all_tests.py` |
| [quick_smoke_test.py](../scripts/quick_smoke_test.py) | ~15 Min | Schneller Sicherheitscheck | `python ./quick_smoke_test.py` |
| [hotfix_smoke_test.py](../scripts/hotfix_smoke_test.py) | ~5 Min | Notfall-Hotfix Absicherung | `python ./hotfix_smoke_test.py` |

## Script Details

### 1. run_all_tests.py - Vollständige Test Suite

**Zweck:** Umfassende Validierung vor Releases  
**Dauer:** ~3 Minuten (abhängig von System)  
**Ausgabe:** Detaillierter Report mit Pass/Fail-Status

**Führt durch:**
1. **Syntax-Check** (py_compile)
   - Python-Syntax der Hauptdatei überprüfen
   - Sofortige Fehler erkennen

2. **Build-Readiness Tests**
   - PyInstaller-Installation prüfen
   - Spec-Datei validieren
   - Abhängigkeiten überprüfen
   - Daten-Dateien prüfen

3. **Quality Suite**
   - Import-Validierung
   - ProgressEngine-Logik
   - Code-Linting
   - Datei-Integrität

**Verwendung:**
```bash
python .github/skills/release-test/scripts/run_all_tests.py
```

**Erfolgs-Kriterium:**
- Alle Tests PASS
- Exit-Code: 0

---

### 2. quick_smoke_test.py - 15 Minuten Quick-Track

**Zweck:** Schneller Sicherheitscheck vor Build/Upload  
**Dauer:** ~15 Minuten  
**Fokus:** Startfähigkeit, Kernpfad, Validator  
**Ausgabe:** Tabellarischer Report mit Zeitstempel

**Prüfungen:**
1. **00-01 Min:** Syntax-Check (py_compile)
2. **01-02 Min:** App-Start und UI-Responsiveness
3. **02-03 Min:** Build-Readiness
4. **03-04 Min:** Quick Quality-Checks

**Verwendung:**
```bash
python .github/skills/release-test/scripts/quick_smoke_test.py
```

**Erfolgs-Kriterium:**
- Alle 4 Prüfungen PASS
- Gesamtdauer < 15 Min
- Exit-Code: 0

**Beispiel-Output:**
```
T+ 00:00 | Syntax-Check (py_compile)
  ✓ PASS  T+00:00  Hauptdatei-Syntax
       PS5ImageConverter_Pro_FINAL_revised.py - OK

T+ 01:00 | App-Start & UI-Responsiveness
  ✓ PASS  T+01:05  Modul-Import
       Hauptdatei laden - OK

...

✓ QUICK SMOKE TEST BESTANDEN!
  → GO für Build/Release
```

---

### 3. hotfix_smoke_test.py - 5 Minuten Notfall-Track

**Zweck:** Schnellstmögliche Mindestabsicherung bei Hotfixes  
**Dauer:** ~5 Minuten  
**Regel:** Nur bei zeitkritischen Hotfixes verwenden  
**Empfehlung:** Danach innerhalb 24h Quick-Smoke durchziehen

**Kritische Checks (5 Stück):**
1. **00-01 Min:** App startet ohne Ausnahme
2. **01-02 Min:** Moduswechsel 1 & 8 funktionieren
3. **02-03 Min:** Syntax gültig
4. **03-05 Min:** Build-Readiness bestanden

**Verwendung:**
```bash
python .github/skills/release-test/scripts/hotfix_smoke_test.py
```

**Erfolgs-Kriterium:**
- Alle 5 kritischen Checks PASS
- Exit-Code: 0

**Notfall-Verdikt:**
- **GO:** Alle Checks bestanden → Hotfix-Release freigegeben
- **NO GO:** Ein Check fehlgeschlagen → KEIN Release

---

## Integration mit der Skill

Verwende in der Release-Test Skill:

```
/release-test
```

Diese wird automatisch:
1. Den ganzen Quellcode analysieren
2. Alle verfügbaren Test-Scripts ausführen
3. Erkannte Probleme kategorisieren
4. Automatische Korrekturen vorschlagen
5. Einen finalen Report präsentieren

---

## Exit Codes

| Code | Bedeutung |
|------|-----------|
| 0 | Alle Tests bestanden - GO für Release |
| 1 | Tests fehlgeschlagen - KEIN Release |
| 130 | Abgebrochen (Ctrl+C) |

---

## Tipps & Best Practices

### Vor dem Release

**Standard-Ablauf (20-25 Min):**
1. Änderungen committen
2. `run_all_tests.py` ausführen
3. `quick_smoke_test.py` als Bestätigung
4. Bei GO: Build & Release

### Bei Zeitdruck (Hotfix)

**Notfall-Ablauf (5 Min):**
1. Kritischen Fix committen
2. `hotfix_smoke_test.py` ausführen
3. Bei GO: Hotfix-Release
4. **Wichtig:** Innerhalb 24h `quick_smoke_test.py` nachziehen!

### Bei Fehlern

**Debugging-Strategie:**
1. `quick_smoke_test.py` für schnelle Diagnose
2. `run_all_tests.py` für detaillierte Fehleranalyse
3. Fehlermeldungen kopieren und in Skill übergeben
4. `/release-test` mit "debug"-Flag für erweiterte Analyse

---

## Skript-Struktur

```
.github/skills/release-test/
├── SKILL.md                   # Hauptdokumentation
├── scripts/
│   ├── run_all_tests.py       # Master-Test Suite
│   ├── quick_smoke_test.py    # 15-Min Quick-Track
│   └── hotfix_smoke_test.py   # 5-Min Notfall-Track
└── references/
    └── test_scripts_reference.md  # Diese Datei
```

---

## Fehlerbehebung

### "ModuleNotFoundError: No module named 'PS5ImageConverter_Pro_FINAL_revised'"
- Überprüfe, ob du im richtigen Verzeichnis bist
- Stelle sicher, dass die Hauptdatei existiert

### "FileNotFoundError: test_build_ready.py not found"
- Scripts müssen vom Projekt-Root ausgeführt werden
- Prüfe den aktuellen Pfad

### Timeout-Fehler
- Build-Readiness kann bei ersten Läufen länger dauern
- Erhöhe Timeout in den Scripts falls nötig

---

## Konfiguration

Um Scripts anzupassen, bearbeite die `TIMEOUT`-Konstanten am Anfang:

```python
timeout=120  # Sekunden
```

Oder passe die Zeitbudgets an:

```python
self.time_budget = 15 * 60  # 15 Minuten in Sekunden
```
