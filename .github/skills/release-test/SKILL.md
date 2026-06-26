---
name: release-test
description: 'Release-Test Skill zur umfassenden Code-Analyse und Validierung. Nutze diese Skill, um den Gesamtquellcode zu analysieren, Fehler und Probleme zu überprüfen, automatische Lösungen zu finden und Code-Qualität sowie Funktionalität zu verbessern.'
argument-hint: 'Optional: Spezifische Dateien oder Bereiche zum Testen (z.B. "ps5_validator", "all")'
user-invocable: true
---

# Release Test Skill

Eine umfassende Skill zur Code-Analyse, Fehlerüberprüfung und automatischen Fehlerbehebung für Releases.

## Wann verwenden

- **Code-Qualität überprüfen**: Vor Release oder Merge-Requests
- **Fehler und Probleme finden**: Linting, Syntax-Fehler, logische Probleme
- **Tests durchführen**: Unit-Tests, Integrationstests, Build-Validierung
- **Code korrigieren**: Automatische Behebung von erkannten Problemen
- **Dokumentation überprüfen**: Konsistenz und Vollständigkeit

## Arbeitsablauf

### 1. Initialisierung & Analyse
- Projektstruktur überprüfen
- Abhängigkeiten und Anforderungen prüfen
- Python-Umgebung konfigurieren
- Alle Python-Dateien identifizieren

### 2. Code-Qualität prüfen
- Syntax-Fehler überprüfen
- Import-Statements validieren
- Code-Standard und Best-Practices überprüfen
- Linting durchführen (PEP 8, etc.)
- Unused-Imports entfernen
- Type-Hints überprüfen

### 3. Logische Überprüfung
- Funktionalität und Logik analysieren
- Fehlerhafte Algorithmen identifizieren
- Edge-Cases und Error-Handling prüfen
- Sicherheitsprobleme erkennen
- Dependency-Zirkularitäten prüfen

### 4. Tests & Validierung
- Existierende Tests ausführen
- Testabdeckung überprüfen
- Build-Prozess validieren
- Anforderungen (requirements.txt) überprüfen
- Konfigurationsdateien validieren

### 5. Automatische Korrekturen
- Erkannte Probleme kategorisieren
- Automatisch behebbar: Syntax, Imports, Formatierung
- Manuell überprüfbar: Logik, Design, Sicherheit
- Alle Änderungen dokumentieren und Vorschläge präsentieren

### 6. Bericht & Nächste Schritte
- Zusammenfassung der Erkenntnisse
- Korrekturen anzeigen (vor/nach)
- Restliche manuelle Tasks auflisten
- Recommendations für Code-Verbesserungen

## Automatisierte Test-Scripts

Diese Skill enthält spezialisierte Test-Scripts für verschiedene Szenarien:

### Scripts im Detail

- **[run_all_tests.py](./scripts/run_all_tests.py)** (~3 Min)
  - Vollständige Syntax-, Build- und Quality-Validierung
  - Standard für vollständige Release-Vorbereitung

- **[quick_smoke_test.py](./scripts/quick_smoke_test.py)** (~15 Min)
  - Schneller Sicherheitscheck vor Build/Upload
  - Fokus: Startfähigkeit, Kernpfad, Validator
  - Ideale Ergänzung zu run_all_tests

- **[hotfix_smoke_test.py](./scripts/hotfix_smoke_test.py)** (~5 Min)
  - Notfall-Absicherung für zeitkritische Hotfixes
  - 5 kritische Checks, Empfehlung: Danach 24h Quick-Smoke

Siehe [Test Scripts Referenz](./references/test_scripts_reference.md) für detaillierte Dokumentation.

## Durchführung

### Option 1: Interaktiv via Skill

Starten Sie die Skill mit dem Befehl:

```
/release-test
```

Optional können Sie Bereiche eingrenzen:
- `/release-test ps5_validator` - Nur ps5_validator-Modul überprüfen
- `/release-test all` - Vollständige Analyse aller Dateien
- `/release-test quick` - Quick-Smoke Test (15 Min)
- `/release-test hotfix` - Notfall-Smoke Test (5 Min)

Die Skill wird dann systematisch durch alle Analysen gehen und bei erkannten Problemen Lösungen vorschlagen und umsetzen.

### Option 2: Direkt Kommandozeile

**Vollständige Test Suite:**
```bash
python .github/skills/release-test/scripts/run_all_tests.py
```

**Quick Smoke (15 Min):**
```bash
python .github/skills/release-test/scripts/quick_smoke_test.py
```

**Notfall Smoke (5 Min):**
```bash
python .github/skills/release-test/scripts/hotfix_smoke_test.py
```

## Release-Entscheidung

| Szenario | Test | Ergebnis | Entscheidung |
|----------|------|----------|--------------|
| Standard Release | `run_all_tests.py` | ✓ alle PASS | → GO für Build |
| Vor Upload | `quick_smoke_test.py` | ✓ alle 4 PASS | → GO für Release |
| Kritischer Hotfix | `hotfix_smoke_test.py` | ✓ alle 5 PASS | → GO, danach 24h Quick-Smoke |
| Beliebiger Test FAIL | beliebig | ✗ FAIL | → Fehler debuggen, Korrekturen durchführen |
