# PS5 Dump & Image Converter

Desktop-Tool (Tkinter) zum Konvertieren, Packen, Entpacken und Validieren von PS5-Dump-Formaten.

Aktueller Stand: v1.7.76

## Funktionen

Die GUI bietet 8 Aufgabenmodi:

1. Game Dump Ordner -> ffpfsc
2. ffpfsc -> exFAT
3. exFAT -> ffpfsc
4. ffpfsc -> Game Dump Ordner
5. exFAT -> Game Dump Ordner
6. ffpkg -> ffpfsc
7. fakelib Manager (Suchen/Loeschen/Hinzufuegen)
8. Dump Validator (Integritaet pruefen)

Validator-Quellen in Aufgabe 8:

- Dump-Ordner
- .ffpfsc
- .ffpfs
- .exfat
- .ffpkg

## Projektstruktur

- PS5ImageConverter_Pro_FINAL_revised.py: Hauptanwendung (GUI + Workflow)
- ps5_validator/: Validator-Paket
- PS5ImageConverter_Pro.spec: PyInstaller-Spec
- Build_EXE.ps1: Build-Skript fuer EXE
- Start_Build.bat: Startet Build-Skript per Doppelklick
- Sign_EXE.ps1: Optionales Code-Signing
- requirements.txt: Python-Abhaengigkeiten

## Voraussetzungen

### Python

- Windows
- Python 3.10+ (empfohlen aktuelle 64-bit Version)

### Python-Pakete

Minimal laut requirements.txt:

- Pillow==12.2.0
- cryptography==49.0.0
- zstandard==0.25.0

Fuer Build/Bundle werden zusaetzlich genutzt:

- pyinstaller
- paramiko

### Externe Tools (je nach Modus)

- OSFMount (fuer exFAT-Mount/Dismount-Workflows)
- UFS2Tool-Daten ueber ps5_ufs2tool_data.py
- FileZilla (Direktstart aus der GUI)

## Installation

Im Projektordner:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller paramiko
```

## Anwendung starten

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

## EXE bauen

### Option A: per Doppelklick

- Start_Build.bat ausfuehren

### Option B: PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\Build_EXE.ps1
```

Ergebnis:

- EXE in dist/
- Name laut Version: PS5_Dump_Image_Converter_v1.7.76.exe

## EXE signieren (optional)

Beispiel mit PFX:

```powershell
.\Sign_EXE.ps1 -ExePath "dist\PS5_Dump_Image_Converter_v1.7.76.exe" -PfxPath "C:\Pfad\zertifikat.pfx" -PfxPassword "<passwort>"
```

Beispiel mit EV-Token:

```powershell
.\Sign_EXE.ps1 -ExePath "dist\PS5_Dump_Image_Converter_v1.7.76.exe" -EV
```

## Konfiguration

- Nutzerbezogene Einstellungen/Pfade werden in einer JSON-Datei gespeichert.
- Unter Windows standardmaessig in APPDATA/PS5ImageConverterPro/paths.json

## Hinweise

- Die EXE kann Administratorrechte anfordern (UAC), insbesondere fuer Mount-Funktionen.
- Antivirus kann bei frischen Builds Warnungen ausloesen (False Positives moeglich).
- Beim Schliessen waehrend laufender Aufgabe erscheint eine Abfrage zum Abbruch.
- Die Quellen-Auswahl merkt sich den zuletzt geoeffneten Pfad (Fallback: Arbeitsplatz/Arbeitsverzeichnis).

## Fehlerbehebung

- Build bricht ab:
	- Python/Pip pruefen
	- Abhaengigkeiten neu installieren
	- Build_EXE.ps1 erneut starten
- OSFMount-Probleme:
	- Tool-Installation und Rechte pruefen
	- Laufwerk ggf. manuell dismounten und erneut versuchen
- GUI startet nicht:
	- Direkt per python starten und Konsolenausgabe pruefen

## Lizenz

Siehe LICENSE.