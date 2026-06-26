# Release Test Scripts - Schnellstart

Automatisierte Test-Scripts zur Validierung und Release-Freigabe des PS5ImageConverter.

## 🚀 Quick Start

### Standard Release-Ablauf (20-25 Min)
```bash
# 1. Vollständige Validierung
python run_all_tests.py

# 2. Quick-Check als Bestätigung
python quick_smoke_test.py

# 3. Bei ✓ - Ready for Release!
```

### Notfall-Hotfix (5 Min)
```bash
# Schnelles Notfall-Smoke
python hotfix_smoke_test.py

# Bei ✓ - Hotfix freigegeben
# ⚠️ Wichtig: Innerhalb 24h Quick-Smoke durchziehen!
```

## 📋 Scripts Übersicht

| Script | Zeit | Was es tut |
|--------|------|-----------|
| `run_all_tests.py` | ~3 Min | ✓ Syntax + ✓ Build + ✓ Quality |
| `quick_smoke_test.py` | ~15 Min | ✓ Start + ✓ UI + ✓ Build + ✓ Quality |
| `hotfix_smoke_test.py` | ~5 Min | ✓ Start + ✓ UI + ✓ Syntax + ✓ Build |

## 📖 Detaillierte Dokumentation

Siehe [test_scripts_reference.md](../references/test_scripts_reference.md) für:
- Ausführliche Script-Beschreibungen
- Erfolgs-Kriterien
- Fehlerbehandlung
- Best Practices

## 🔄 Integration mit Release-Test Skill

Alternativ zur direkten Ausführung kannst du die Skill verwenden:

```
/release-test
```

Die Skill automatisiert die komplette Analyse und Fehlerbehebung.

## ⚙️ Anforderungen

- Python 3.8+
- Alle Dependencies aus `requirements.txt` installiert
- Hauptdatei: `PS5ImageConverter_Pro_FINAL_revised.py`
- Test-Dateien: `test_build_ready.py`, `test_all_quality.py`

## 📊 Exit Codes

- **0** = Alle Tests bestanden → GO für Release
- **1** = Tests fehlgeschlagen → KEIN Release
- **130** = Durch Benutzer abgebrochen (Ctrl+C)

## 🐛 Problembehebung

### Script findet Hauptdatei nicht?
```bash
# Stelle sicher du im Projekt-Root bist:
cd /path/to/PS5ImageConverter/project/
python .github/skills/release-test/scripts/run_all_tests.py
```

### ModuleNotFoundError?
```bash
# Install dependencies
pip install -r requirements.txt
```

### Lange Laufzeiten?
- Erste Läufe können länger dauern
- Build-Readiness cached nach erstem Lauf
- Erhöhe `timeout` in den Scripts bei Bedarf

## ✅ Checklisten

### Vor Vollständiger Release
- [ ] `run_all_tests.py` → ✓
- [ ] `quick_smoke_test.py` → ✓
- [ ] Code-Änderungen dokumentiert
- [ ] Changelog aktualisiert
- [ ] Version bumped
- → Ready for Build & Upload

### Vor Hotfix-Release
- [ ] `hotfix_smoke_test.py` → ✓
- [ ] Kritischer Fix getestet
- [ ] Version hotfix bumped
- → Ready for Quick Upload
- [ ] ⚠️ Reminder: 24h Quick-Smoke durchziehen!

## 💡 Tipps

- **Vor wichtigen Releases:** `run_all_tests.py` + `quick_smoke_test.py`
- **Regelmäßig:** `quick_smoke_test.py` auch während Entwicklung nutzen
- **Bei Problemen:** Starten mit `hotfix_smoke_test.py` für schnelle Diagnose
- **Debug-Mode:** Scripts haben ausführliche Fehlerausgaben

## 📞 Support

Fehler oder Fragen? Siehe [test_scripts_reference.md](../references/test_scripts_reference.md) Sektion "Fehlerbehebung" oder nutze `/release-test` für erweiterte Diagnose.

---

**Letztes Update:** 2026-06-26  
**Skill Version:** 1.0  
**Python:** 3.8+
