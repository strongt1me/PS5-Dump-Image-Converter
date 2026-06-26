# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

## [Unreleased] - 2026-06-26

### Hinzugefuegt
- Ressourcen-Fenster erweitert um 3 neue Aktionen fuer automatische Hintergrund-Installation:
  - [19] OSFMount
  - [20] Dokan2
  - [21] FileZilla
- Neue Dokumente:
  - DOKUMENTATION_RELEASE.md
  - DOKUMENTATION_19_21.md

### Geaendert
- Installer-Flow 19-21 prueft vor Download/Setup zuerst, ob das jeweilige Tool bereits installiert ist.
- Status-/Dialogtexte fuer 19-21 vereinheitlicht und mit Aufgaben-Praefix [19]/[20]/[21] versehen.

### Behoben
- Thread-sichere UI-Updates in Hintergrundpfaden gehaertet (RuntimeError bei Shutdown/Mainloop-Rennen abgefangen).

## [v1.7.76] - 2026-06-25

### Hinzugefuegt
- FileZilla-Erkennung erweitert, inkl. Portable-Layouts im App-Verzeichnis.
- Automatische FileZilla-Installation (Windows) mit Nutzerabfrage (Download + Setup).
- Verbesserter FileZilla-Startablauf mit manueller EXE-Auswahl als Fallback.
- Quick-Connect-Verwaltung fuer FileZilla (Einrichten, Bearbeiten, Loeschen, Passwort loeschen).
- Persistenter Startordner fuer Quellauswahl (last_source_dir).
- Erweiterte Dump-Validator-Unterstuetzung fuer Eingaben:
  - Ordner
  - .ffpfsc
  - .ffpfs
  - .exfat
  - .ffpkg
- Schnellpruefung/Vollpruefung-Auswahl im Validator fuer Datei-Quellen.

### Geaendert
- Versionsstand auf v1.7.76 aktualisiert in:
  - Build-Skript
  - PyInstaller-Spec
  - Hauptanwendung
- Titelleisten-Button von FTP auf FILEZILLA umgestellt.
- Diverse GUI-Texte und Tooltips praezisiert.
- Robustheit bei optionalen GUI-Elementen verbessert (z. B. Maximize-Button-Zugriffe).
- Subprozess-Helfer erweitert:
  - optionale Parameter fuer Encoding, Errors, cwd, env
  - zeilenweiser Callback fuer Ausgabe
- Quelle/Ziel-Validierung in mehreren Modi verfeinert.
- Verhalten beim Beenden waehrend laufender Aufgaben verbessert (Abbruchfluss klarer, Thread-Stop-Signal).

### Behoben
- Mehrere statische Analyse-/Typwarnungen in kritischen Pfaden der Hauptdatei reduziert.
- Potenziell unsichere optionale Zugriffe auf Widgets abgesichert.
- Mehrere Import-/Typing-Hinweise fuer externe mkpfs-Module gezielt entschärft.
- Robustere Behandlung bei Prozess-Timeouts und Prozessabbruch.

### Entfernt
- Nicht relevante Hilfs-/Patch-/Testskripte aus dem Projektroot entfernt (historische Einmal-Skripte).
- Cache-/Artefaktdateien bereinigt:
  - __pycache__
  - .pyc
  - .pytest_cache
- Auf Wunsch entfernt:
  - .venv
  - .vscode/settings.json

### Dokumentation
- README deutlich erweitert (Projektbeschreibung, Modi, Voraussetzungen, Build/Signierung, Hinweise, Troubleshooting).
- requirements.txt im Projekt hinterlegt/aktualisiert mit:
  - Pillow==12.2.0
  - cryptography==49.0.0
  - zstandard==0.25.0

### Validierung und Tests
- Syntax-/Kompilationspruefungen erfolgreich:
  - py_compile fuer Hauptdatei
  - compileall fuer Projekt
- Laufzeittests fuer Validator erfolgreich (Exit-Code 0):
  - --help
  - dump-Modus
  - ffpfs-Modus
  - extfat-Modus
- Dateien fuer Smoke-Tests wurden nach dem Testlauf wieder entfernt.

### Hinweis
- Neben den hier dokumentierten Produktivänderungen wurden im Verlauf auch viele historische Entwicklungs-/Patch-Dateien aus dem Arbeitsstand entfernt. Dieser Changelog fokussiert die fuer den aktuellen Projektstand relevanten Ergebnisänderungen.
