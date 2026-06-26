# Release-Test Skill - Komplette Struktur

```
.github/skills/release-test/
│
├── SKILL.md                           # ← Hauptdokumentation (du starten hier)
│
├── scripts/                           # Test-Scripts
│   ├── README.md                      # Quick-Start für Scripts
│   ├── run_all_tests.py               # ★ Master Suite (~3 Min)
│   ├── quick_smoke_test.py            # ★ 15-Min Track
│   └── hotfix_smoke_test.py           # ★ 5-Min Notfall
│
└── references/                        # Dokumentation
    └── test_scripts_reference.md      # Detaillierter Guide für alle Scripts
```

---

## 🎯 Workflow nach Zweck

### Normaler Release (Standard-Vorbereitung)
```
Entwicklung
    ↓
/release-test (Skill)
    ↓
Automatische Code-Analyse & Korrekturen
    ↓
run_all_tests.py (automatisch durchgeführt)
    ↓
✓ Alle Tests bestanden
    ↓
quick_smoke_test.py (als Bestätigung)
    ↓
✓ GO für Build
    ↓
Build & Release
```

### Schneller Release (vor Upload)
```
Code bereit
    ↓
quick_smoke_test.py
    ↓
✓ 15-Min Tests bestanden
    ↓
GO für Upload
```

### Notfall-Hotfix (zeitkritisch)
```
Kritischer Fix gemacht
    ↓
hotfix_smoke_test.py
    ↓
✓ 5 kritische Checks bestanden
    ↓
GO für Quick-Release
    ↓
⚠️ Reminder: 24h später Quick-Smoke durchziehen
    ↓
quick_smoke_test.py (Nachziehen)
    ↓
✓ Alles validiert
```

---

## 📚 Dokumentation Navigation

| Wenn du... | Gehe zu... |
|-----------|-----------|
| Anfänger bist | [SKILL.md](SKILL.md) |
| Scripts direkt nutzen willst | [scripts/README.md](scripts/README.md) |
| Details zu jedem Script brauchst | [references/test_scripts_reference.md](references/test_scripts_reference.md) |
| Ein spezifisches Problem hast | [references/test_scripts_reference.md#fehlerbehebung](references/test_scripts_reference.md#fehlerbehebung) |

---

## 🚀 Einsteiger-Guide

### 1. Erste Verwendung
```bash
# Gehe zum Projekt-Verzeichnis
cd /path/to/PS5ImageConverter/

# Starte die volle Test-Suite
python .github/skills/release-test/scripts/run_all_tests.py
```

### 2. Ergebnis überprüfen
```
✓ alle Tests bestanden → du bist ready!
✗ Fehler gefunden → nutze /release-test für Auto-Fixes
```

### 3. Für Release freigeben
```bash
# Schnelle Bestätigung
python .github/skills/release-test/scripts/quick_smoke_test.py
```

---

## 🎨 Farb-Legende in Script-Ausgaben

- 🟢 **Grün** = Test bestanden ✓
- 🔴 **Rot** = Test fehlgeschlagen ✗
- 🟡 **Gelb** = Warnung ⚠️
- 🔵 **Blau** = Header/Info ℹ️

---

## ⚡ Performance

| Operation | Dauer | Hardware-abhängig |
|-----------|-------|------------------|
| run_all_tests | ~3 Min | Ja, erste Läufe langsamer |
| quick_smoke_test | ~15 Min | Ja, je nach SSD-Speed |
| hotfix_smoke_test | ~5 Min | Minimal |

**Tipp:** Laufe alle Scripts nacheinander, damit caches aufwärmen.

---

## 🔗 Integration mit der Skill

Alle diese Scripts werden automatisch aufgerufen, wenn du nutzt:

```
/release-test
```

Diese Skill:
1. Liest alle Scripts
2. Führt sie intelligently aus
3. Analysiert die Ergebnisse
4. Schlägt automatische Fixes vor
5. Dokumentiert alles

---

## 📋 Checkliste vor Release

- [ ] Alle Änderungen committed
- [ ] `python run_all_tests.py` → ✓
- [ ] `python quick_smoke_test.py` → ✓
- [ ] Changelog.md aktualisiert
- [ ] Version in `PS5ImageConverter_Pro.spec` erhöht
- [ ] Build-Spec validiert
- [ ] Ready for `./Start_Build.bat`
- [ ] Ready for Release

---

## 🆘 Schnelle Hilfe

**Problem:** "ModuleNotFoundError"
→ Installiere: `pip install -r requirements.txt`

**Problem:** Script findet Hauptdatei nicht
→ Stelle sicher: Du bist im Projekt-Root: `cd /path/to/Mein-erstes-Projekt`

**Problem:** Sehr lange Laufzeit
→ Das ist normal bei ersten Läufen. Caches werden aufgebaut.

**Problem:** Tests schlagen fehl
→ Nutze `/release-test` für detaillierte Diagnose und automatische Fixes

---

## 📞 Weitere Hilfe

Siehe die Dokumentation in dieser Skill:
- **SKILL.md** - Übersicht und Arbeitsablauf
- **scripts/README.md** - Quick-Start für Scripts
- **references/test_scripts_reference.md** - Detaillierte Dokumentation

Viel Erfolg mit deinem Release! 🚀
