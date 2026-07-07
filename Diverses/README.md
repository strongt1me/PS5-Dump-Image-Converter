# PS5 Dump & Image Converter

Desktop-Tool (Tkinter) zum Konvertieren, Packen, Entpacken und Validieren von PS5-Dump-Formaten.

Aktueller Stand: v1.7.80

## Dokumentation

- [Kurz-Anleitung](KURZANLEITUNG.md): Schneller Einstieg fuer die wichtigsten Arbeitsablaeufe
- [Release-Dokumentation](DOKUMENTATION_RELEASE.md): Build-, Test- und Release-Stand

Weitere Kurzfassungen und Sonderdokumente liegen gesammelt in diesem Ordner.

## Funktionen

Die Anwendung konzentriert sich auf die wichtigsten PS5-Dump-Workflows:

- Konvertieren zwischen Dump-Ordner, .ffpfsc und .exfat
- Umwandeln von .ffpkg nach .ffpfsc
- Bearbeiten von fakelib- und Root-Dateien in unterstuetzten Quellen
- Automatische Erzeugung von `ampr_emu.index` in Aufgabe 7 bei erkanntem `fakelib/libSceAmpr.sprx`
- Validieren von Dump-Strukturen und Artefakten
- GUI-gestuetzte Workflows mit Build-, Logging- und Admin-Helfern

Fuer grosse Images nutzt die App adaptive Standard-Presets, um RAM-Spitzen zu reduzieren und reproduzierbare Ergebnisse ohne manuelles Fine-Tuning zu liefern.

## Kernbestandteile

- PS5ImageConverter_Pro_FINAL_revised.py: Hauptanwendung
- ps5_validator/: Validator-Paket
- Build_EXE.ps1: EXE-Build
- requirements.txt: Python-Abhaengigkeiten

## Voraussetzungen

- Windows
- Python 3.10 oder neuer, idealerweise 64-bit
- Ausreichend freier Speicherplatz fuer Temp- und Ausgabe-Dateien
- OSFMount und Administratorrechte fuer exFAT- und Mount-Workflows

## Schnellstart

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

```powershell
powershell -ExecutionPolicy Bypass -File .\Build_EXE.ps1
```

Ergebnis: EXE in dist/ als PS5_Dump_Image_Converter_v1.7.80.exe

## EXE signieren (optional)

Der aktuelle Projektstand enthaelt keinen aktiven Signier-Workflow im Repo. Ohne Code-Signing-Zertifikat bleibt die EXE technisch nutzbar, kann aber von SmartScreen oder Antivirus vorsichtiger behandelt werden.

## Konfiguration

- Einstellungen und Pfade werden unter Windows standardmaessig in APPDATA/PS5ImageConverterPro/paths.json gespeichert.

## Hinweise

- Die EXE kann Administratorrechte anfordern, insbesondere fuer Mount-Funktionen.
- Frische Builds koennen durch Antivirus oder SmartScreen zunaechst auffallen.
- Laufende Aufgaben lassen sich mit Rueckfrage abbrechen; zuletzt genutzte Quellpfade werden gemerkt.
- Aufgabe 7 erzeugt `ampr_emu.index` automatisch neu, wenn ein AMPR-Emulations-Build ueber `fakelib/libSceAmpr.sprx` erkannt wird.

## Automatische Installation (Ressourcen 19-21)

Im Ressourcen-Fenster koennen OSFMount, Dokan2 und FileZilla bei Bedarf im Hintergrund installiert werden. Bereits vorhandene Installationen werden erkannt und uebersprungen.

## Fehlerbehebung

- Build bricht ab: Python/Pip pruefen, Abhaengigkeiten neu installieren, Build_EXE.ps1 erneut starten.
- OSFMount-Probleme: Installation, Rechte und gemountete Laufwerke pruefen.
- GUI startet nicht: Direkt per python starten und die Konsolenausgabe pruefen.

## Lizenz

Siehe LICENSE.