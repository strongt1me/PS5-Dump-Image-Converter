# PS5 Dump & Image Converter

![Platform](https://img.shields.io/badge/platform-Windows-0078D6)
![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)
![Status](https://img.shields.io/badge/status-release--ready-brightgreen)
![Version](https://img.shields.io/badge/version-v1.7.80-blue)

Windows-Desktop-Tool zum Konvertieren, Packen, Entpacken, Validieren und Bearbeiten von PS5-Dump-Formaten.

Das Projekt kombiniert einen GUI-Workflow mit nativen MkPFS-basierten Pfaden, gezielten Admin-Helfern und automatisierter Validierung fuer die wichtigsten Aufgabenpfade.

## Inhalt

- [Aktueller Status](#aktueller-status)
- [Hauptfunktionen](#hauptfunktionen)
- [Unterstuetzte Aufgaben](#unterstuetzte-aufgaben)
- [Wichtige Hinweise](#wichtige-hinweise)
- [Voraussetzungen](#voraussetzungen)
- [Schnellstart](#schnellstart)
- [Gezielte Admin-Laeufe](#gezielte-admin-laeufe)
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
- Frischer EXE-Build: `dist/PS5_Dump_Image_Converter_v1.7.80.exe`
- Gezielte Admin-Validierung fuer Aufgabe 7 mit `.ffpkg`: PASS
- Sichtbarer Nachweis fuer Restgroesse und ETA in der Hauptphase von Aufgabe 7 `.ffpkg`: PASS

Beste aktuelle Referenzartefakte:
- Admin-Validierungsbericht fuer Aufgabe 7 `.ffpkg`: `_e2e_output_a7_ffpkg_admin_live_20260708_ui_finalproof/e2e_report_a7.json`
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
- `ampr_emu.index` fuer Aufgabe 7 automatisch erzeugen, wenn `fakelib/libSceAmpr.sprx` vorhanden ist
- Dump-Strukturen und Artefakte validieren
- Eine eigenstaendige Windows-EXE mit PyInstaller bauen

## Fuer Wen Das Ist

- Nutzer, die eine Windows-GUI fuer gaengige PS5-Dump-Konvertierungs-Workflows wollen
- Nutzer, die wiederholbare, admin-unterstuetzte Validierung fuer ausgewaehlte Aufgaben benoetigen
- Homebrew-orientierte Workflows, die von MkPFS-basierten Pack- und Extraktionspfaden profitieren

## Unterstuetzte Aufgaben

1. Game dump folder -> `.ffpfsc`
2. `.ffpfsc` -> `.exfat`
3. `.exfat` -> `.ffpfsc`
4. `.ffpfsc` -> game dump folder
5. `.exfat` -> game dump folder
6. `.ffpkg` -> `.ffpfsc`
7. `fakelib` manager for folder / `.ffpfsc` / `.exfat` / `.ffpkg`
8. Dump validator

## Wichtige Hinweise

- Aufgaben 1, 2, 4 und 5 koennen Administratorrechte benoetigen.
- Aufgabe 7 mit `.ffpkg` als Quelle benoetigt in der Regel ebenfalls Administratorrechte, weil die Extraktion den UFS2Tool-/Dokan-Pfad nutzt.
- Fuer Aufgabe 7 wird `.ffpkg` als Eingabeformat unterstuetzt, das bearbeitete Ergebnis wird aber als `.ffpfsc` geschrieben.
- Aufgabe 7 erzeugt `ampr_emu.index` automatisch neu, sobald ein AMPR-Emulationsmarker (`fakelib/libSceAmpr.sprx`) erkannt wird.
- Fuer exFAT-bezogene Workflows muss OSFMount installiert und nutzbar sein.
- Der Validator soll unvollstaendige oder unplausible Dump-Strukturen frueh erkennen.

## Voraussetzungen

- Windows
- Python 3.10 oder neuer fuer den `.py`-Workflow
- Genug freier Speicherplatz fuer temporaere Dateien und Ausgabe-Artefakte
- Administratorrechte fuer erhoehte Workflows

Die Python-Abhaengigkeiten sind in `requirements.txt` definiert.

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
dist/PS5_Dump_Image_Converter_v1.7.80.exe
```

## Typische Workflows

### Einen Spiel-Dump-Ordner nach `.ffpfsc` konvertieren

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

Danach Aufgabe 1 waehlen, den Dump-Ordner auswaehlen, ein Ausgabeziel festlegen und den Lauf starten.

### `fakelib` aus einer `.ffpkg`-Quelle bearbeiten

1. Anwendung starten
2. Aufgabe 7 waehlen
3. Eine `.ffpkg`-Quelle auswaehlen
4. UAC bzw. Administratorrechte bestaetigen, falls noetig
5. `fakelib`- oder Root-Datei-Aenderungen anwenden
6. Ergebnis als `.ffpfsc` speichern

## Gezielte Admin-Laeufe

Das Repository enthaelt einen erhoehten Runner fuer die gezielte Validierung einzelner Aufgaben:

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

- `Build_EXE.ps1` fuer den Windows-EXE-Build-Ablauf
- `Run_Tasks_1_8_Admin.ps1` fuer die erhoehte Einzelaufgaben-Validierung

## Projektdateien

- `PS5ImageConverter_Pro_FINAL_revised.py`: Haupt-GUI-Anwendung und Aufgabenlogik
- `run_tasks_1_8_e2e.py`: automatisierter Aufgaben-Runner
- `Run_Tasks_1_8_Admin.ps1`: erhoehter Runner fuer gezielte Admin-Validierung
- `Build_EXE.ps1`: PyInstaller-Build-Skript
- `test_all_quality_new.py`: aktueller Einstiegspunkt fuer die Quality Suite
- `test_build_ready.py`: Build-Readiness-Pruefungen

## Credits

Spezialversion von Strongt1me.

Core-Engine:
- Phoenixx1202 / PSBrew for MkPFS v0.0.9

Weitere Grundlagen und Community-Beitraege:
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

## Dank

Dieses Projekt baut auf der Arbeit der PS5-Homebrew-Community und des Open-Source-Oekosystems darum herum auf.

Ein besonderer Dank geht an alle, die Forschung, Code, Werkzeuge und praktisches Wissen teilen, damit andere darauf aufbauen, daraus lernen und die Szene weiterbringen koennen.

Das schliesst ausdruecklich auch kerrdec97 als Entwickler hinter PS5 exFAT Image Builder / ps5-exfat-builder ein, dessen veroeffentlichte Grundlagen und Werkzeuge wichtige Workflow-Richtungen dieses Projekts mitgepraegt haben.

## Lizenz / Hinweis

Vor einer Weiterverteilung sollten die Repository-Dateien und die Lizenzen der gebuendelten Werkzeuge geprueft werden. Unterschiedliche integrierte Tools und Abhaengigkeiten koennen eigene Lizenzbedingungen haben.
