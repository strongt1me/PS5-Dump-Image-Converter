# Full Test Suite Skill

Automatisierte vollständige Validierung aller Komponenten des PS5 Image Converters.

## Quick Start

```bash
# Vollständige Test Suite
/full-test

# Oder via Kommandozeile:
python .github/skills/release-test/scripts/run_all_tests.py
```

## Test-Modi

### 1. **Vollständige Suite** (Standard, ~3 Min)
```bash
/full-test
# oder
python .github/skills/release-test/scripts/run_all_tests.py
```
- Syntax-Check
- Build-Readiness
- Code-Quality

### 2. **Quick Smoke Test** (~15 Min)
```bash
/full-test quick
# oder
python .github/skills/release-test/scripts/quick_smoke_test.py
```
- App-Start
- Build-Readiness
- Quality-Checks

### 3. **Hotfix Emergency** (~5 Min)
```bash
/full-test hotfix
# oder
python .github/skills/release-test/scripts/hotfix_smoke_test.py
```
- 5 kritische Checks
- Schnelle Validierung

## Ergebnis-Interpretation

| Exit Code | Bedeutung |
|-----------|-----------|
| 0 | ✓ ALLE TESTS BESTANDEN - GO FÜR RELEASE |
| 1 | ✗ FEHLER - Hinweise in der Ausgabe |

## Struktur

```
.github/skills/full-test/
├── SKILL.md              # Skill-Dokumentation
├── README.md             # Diese Datei
└── scripts/
    └── dispatcher.py     # Orchesriert alle Test-Modi
```

## Best Practices

- **Vor Commits**: `quick_smoke_test.py`
- **Vor Releases**: `run_all_tests.py`
- **Bei Hotfixes**: `hotfix_smoke_test.py` + danach 24h `quick_smoke_test.py`

## Verwandte Skills

- **release-test**: Einzelne Test-Komponenten
- Siehe `.github/skills/release-test/SKILL.md` für Details
