# PS5 Dump & Image Converter

![Plattform](https://img.shields.io/badge/Plattform-Windows-0078D6)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Status](https://img.shields.io/badge/Status-release--bereit-brightgreen)
![Version](https://img.shields.io/badge/Version-v1.7.81-blue)

Windows-Desktop-Tool zum Konvertieren, Packen, Entpacken, Validieren und Bearbeiten von PS5-Dump-Formaten.

Das Projekt kombiniert einen GUI-Workflow mit nativen MkPFS-basierten Pfaden, gezielten Admin-Helfern und automatisierter Validierung für die wichtigsten Aufgabenpfade.

## Inhalt

- [Aktueller Status](#aktueller-status)
- [Hauptfunktionen](#hauptfunktionen)
- [Unterstützte Aufgaben](#unterstützte-aufgaben)
- [Wichtige Hinweise](#wichtige-hinweise)
- [Voraussetzungen](#voraussetzungen)
- [Schnellstart](#schnellstart)
- [Gezielte Admin-Läufe](#gezielte-admin-läufe)
- [Validierung](#validierung)
- [Projektdateien](#projektdateien)
- [Dokumentation](#dokumentation)
- [Credits](#credits)
- [Dank](#dank)
- [Lizenz / Hinweis](#lizenz--hinweis)

## Aktueller Status

Release-bereit auf dem aktuellen `main`-Branch.

Validiert auf dem aktuellen Release-Stand mit:
- Quality Suite: 8/8 PASS
- Build Readiness: 7/7 PASS
- Frischer EXE-Build: `dist/PS5_Dump_Image_Converter_v1.7.81.exe`
- Gezielte Admin-Validierung für Aufgabe 7 mit `.ffpkg`: PASS
- Sichtbarer Nachweis für Restgröße und ETA in der Hauptphase von Aufgabe 7 `.ffpkg`: PASS

Beste aktuelle Referenzartefakte:
- Admin-Validierungsbericht für Aufgabe 7 `.ffpkg`: `_e2e_output_a7_ffpkg_admin_live_20260708_ui_finalproof/e2e_report_a7.json`
- Build-Skript: `Build_EXE.ps1`
- Hauptanwendung: `PS5ImageConverter_Pro_FINAL_revised.py`

## Hauptfunktionen

- PS5-Spiel-Dump-Ordner nach `.ffpfsc` packen
- `.ffpfsc` nach `.exfat` konvertieren
- `.exfat` nach `.ffpfsc` konvertieren
- `.ffpfsc` in einen Spiel-Dump-Ordner entpacken
- `.exfat` in einen Spiel-Dump-Ordner entpacken
- `.ffpkg` nach `.ffpfsc` konvertieren
- `fakelib` und Root-Dateien in Dump-Quellen verwalten
- `ampr_emu.index` für Aufgabe 7 automatisch erzeugen, wenn `fakelib/libSceAmpr.sprx` vorhanden ist
- Dump-Strukturen und Artefakte validieren
- Eine eigenständige Windows-EXE mit PyInstaller bauen

## Für Wen Das Ist

- Nutzer, die eine Windows-GUI für gängige PS5-Dump-Konvertierungs-Workflows wollen
- Nutzer, die wiederholbare, admin-unterstützte Validierung für ausgewählte Aufgaben benötigen
- Homebrew-orientierte Workflows, die von MkPFS-basierten Pack- und Extraktionspfaden profitieren

## Unterstützte Aufgaben

1. Game dump folder -> `.ffpfsc`
2. `.ffpfsc` -> `.exfat`
3. `.exfat` -> `.ffpfsc`
4. `.ffpfsc` -> game dump folder
5. `.exfat` -> game dump folder
6. `.ffpkg` -> `.ffpfsc`
7. `fakelib` manager for folder / `.ffpfsc` / `.exfat` / `.ffpkg`
8. Dump validator

## Wichtige Hinweise

- Aufgaben 1, 2, 4 und 5 können Administratorrechte benötigen.
- Aufgabe 7 mit `.ffpkg` als Quelle benötigt in der Regel ebenfalls Administratorrechte, weil die Extraktion den UFS2Tool-/Dokan-Pfad nutzt.
- Für Aufgabe 7 wird `.ffpkg` als Eingabeformat unterstützt, das bearbeitete Ergebnis wird aber als `.ffpfsc` geschrieben.
- Aufgabe 7 erzeugt `ampr_emu.index` automatisch neu, sobald ein AMPR-Emulationsmarker (`fakelib/libSceAmpr.sprx`) erkannt wird.
- Für exFAT-bezogene Workflows muss OSFMount installiert und nutzbar sein.
- Der Validator soll unvollständige oder unplausible Dump-Strukturen früh erkennen.

## Voraussetzungen

- Windows
- Python 3.10 oder neuer für den `.py`-Workflow
- Genug freier Speicherplatz für temporäre Dateien und Ausgabe-Artefakte
- Administratorrechte für erhöhte Workflows

Die Python-Abhängigkeiten sind in `requirements.txt` definiert.

## Schnellstart

### Python-Version starten

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

### EXE bauen

```powershell
.\Build_EXE.ps1
```

### Gebaute EXE starten

Starte die erzeugte Datei aus:

```text
dist/PS5_Dump_Image_Converter_v1.7.81.exe
```

## Typische Workflows

### Einen Spiel-Dump-Ordner nach `.ffpfsc` konvertieren

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

Danach Aufgabe 1 wählen, den Dump-Ordner auswählen, ein Ausgabeziel festlegen und den Lauf starten.

Hinweis zur Fortschrittsanzeige in Aufgabe 1:
Der Balken zeigt den Gesamtfortschritt des One-Pass-Laufs über Analyse, Lesen und Kompression. Die Live-Zeile mit `Kompr.`, `Rest` und `ETA` beschreibt dagegen gezielt den aktuellen Kompressionsschritt von MkPFS.

### `fakelib` aus einer `.ffpkg`-Quelle bearbeiten

1. Anwendung starten
2. Aufgabe 7 wählen
3. Eine `.ffpkg`-Quelle auswählen
4. UAC bzw. Administratorrechte bestätigen, falls nötig
5. `fakelib`- oder Root-Datei-Änderungen anwenden
6. Ergebnis als `.ffpfsc` speichern

## Gezielte Admin-Läufe

Das Repository enthält einen erhöhten Runner für die gezielte Validierung einzelner Aufgaben:

```powershell
.\Run_Tasks_1_8_Admin.ps1 -Task A7 -Dump .\path\to\DumpFolder -Ffpkg ".\path\to\input.ffpkg" -OutputDir .\_e2e_output_a7_admin
```

## Validierung

### Quality Suite

```powershell
python test_all_quality_new.py
```

### Build Readiness

```powershell
python test_build_ready.py
```

### End-to-End-Runner

```powershell
python run_tasks_1_8_e2e.py --task A7 --dump .\path\to\DumpFolder --ffpkg ".\path\to\input.ffpkg" --output-dir .\_e2e_output_a7
```

## Dokumentation

- `Build_EXE.ps1` für den Windows-EXE-Build-Ablauf
- `Run_Tasks_1_8_Admin.ps1` für die erhöhte Einzelaufgaben-Validierung

## Projektdateien

- `PS5ImageConverter_Pro_FINAL_revised.py`: Haupt-GUI-Anwendung und Aufgabenlogik
- `run_tasks_1_8_e2e.py`: automatisierter Aufgaben-Runner
- `Run_Tasks_1_8_Admin.ps1`: erhöhter Runner für gezielte Admin-Validierung
- `Build_EXE.ps1`: PyInstaller-Build-Skript
- `test_all_quality_new.py`: aktueller Einstiegspunkt für die Quality Suite
- `test_build_ready.py`: Build-Readiness-Prüfungen

## Credits

Core-Engine:
- Phoenixx1202 / PSBrew for MkPFS v0.0.9

Weitere Grundlagen und Community-Beiträge:
- KryoMod
- Renan Barreto
- Y2JB / PS5 Scene Community
- kerrdec97 for PS5 exFAT Image Builder / ps5-exfat-builder

Integrierte Werkzeuge und technische Grundlagen:
- PassMark Software for OSFMount
- Dokan project
- UFS2Tool authors
- PyInstaller project
- paramiko
- Pillow
- cryptography
- zstandard
- zlib-ng

## Danksagung

Dieses Projekt baut auf der Arbeit der PS5-Homebrew-Community und des Open-Source-Ökosystems darum herum auf.

Ein besonderer Dank geht an alle, die Forschung, Code, Werkzeuge und praktisches Wissen teilen, damit andere darauf aufbauen, daraus lernen und die Szene weiterbringen können.

Das schließt ausdrücklich auch kerrdec97 als Entwickler hinter PS5 exFAT Image Builder / ps5-exfat-builder ein, dessen veröffentlichte Grundlagen und Werkzeuge wichtige Workflow-Richtungen dieses Projekts mitgeprägt haben.

## Lizenz / Hinweis

Vor einer Weiterverteilung sollten die Repository-Dateien und die Lizenzen der gebündelten Werkzeuge geprüft werden. Unterschiedliche integrierte Tools und Abhängigkeiten können eigene Lizenzbedingungen haben.
