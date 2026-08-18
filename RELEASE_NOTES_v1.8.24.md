# PS5 Dump & Image Converter v1.8.24 – Release Notes

## Zweck dieses Releases

Version **v1.8.24** ergänzt vier neue, von Referenz-Konkurrenzprogrammen inspirierte Werkzeuge (Y2JB, MicroMount, AMPR-Index-Builder, Dump-Rename), räumt die dadurch überfüllte Titelleiste wieder auf, und macht die Speicherplatz-Vorabprüfung vor Aufgabe 2/4 deutlich realistischer.

## Änderungen im Einzelnen

### 1. Vier neue Werkzeuge

- **Y2JB** (`_show_y2jb_install`): Reine Installationshilfe – sendet eine vom Nutzer gewählte YouTube-App-PKG-Datei (Region USA/EU/JP, feste erwartete Dateinamen) per HTTP-Multipart-Upload an `http://<PS5-IP>:<DPI-Port>/upload`, den Standard-Endpunkt von etaHENs "Direct Package Installer V2". Mit Fortschrittsbalken, Geschwindigkeitsanzeige und Log. Bewusst nur die Install-Funktion umgesetzt (kein Patch/Autoloader), da diese Teile in Systemdateien der PS5 eingreifen.
- **MicroMount** (`_show_micromount_editor`): Nutzt den bereits bestehenden generischen Konfigurationseditor (`_show_remote_ini_editor`, bisher nur für ShadowMount+), jetzt mit `_MICROMOUNT_REMOTE_CONFIG`/`_MICROMOUNT_DEFAULTS` (echte Standardwerte aus der Referenzdokumentation übernommen). Der generische Editor wurde um einen neuen, optionalen Parameter `payload_default_port` erweitert, der bei Angabe eine zusätzliche Payload-Sektion (Datei wählen + per TCP senden, wiederverwendet dieselbe Technik wie der bestehende JS-Loader) einblendet – ShadowMount+ bleibt davon unberührt (Parameter dort weiterhin `None`).
- **AMPR-Index-Builder** (`_show_ampr_index_builder`, `_build_ampr_index_local`, `_ampr_build_hash_slots`, `_ampr_fnv1a64_path_hash`): Baut aus einem lokalen Ordner eine binäre `AMPRIDX3`-Indexdatei (Header, sortierte Records, Pfad-Blob, Open-Addressing-Hashtabelle mit FNV-1a-64) für den AMPR-Dateiresolver. Bitgenau nach dem Referenzformat portiert; ein Rundlauf-Test verifiziert Header-Felder, Record-Anzahl und Pfade exakt.
- **Dump-Rename** (`_show_dump_rename_window`): Scannt einen Ordner nach direkten Unterordnern, liest deren Metadaten über die bereits bestehende `_read_game_meta`, und schlägt einen neuen Namen nach drei Mustern vor (nur Titel-ID / +Name / +Name+Version). Konfidenz-Ampel: Grün (gültige Titel-ID + Name gefunden), Gelb (Titel-ID gültig, Name fehlt), Rot (keine gültige Titel-ID). Nutzt die bestehende `_is_valid_title_id`-Prüfung.

Alle vier sind über einen neuen Knopf "Weitere Tools ▾" in der Titelleiste erreichbar (Dropdown-Menü statt vier Einzelknöpfen).

### 2. Titelleiste aufgeräumt

Nach dem Hinzufügen der vier neuen Werkzeuge als Einzelknöpfe überlief die Titelleiste bereits bei Standardfenstergröße (1366px) – der Sprachumschalter (EN/DE) fiel dadurch aus dem sichtbaren Bereich. Behoben durch zwei Maßnahmen:
- Der bislang links stehende Programmname/Versions-Text (`self._titlebar_left`) wurde vollständig entfernt.
- Die vier neuen Werkzeuge wurden zu einem einzigen "Weitere Tools ▾"-Knopf mit `tk.Menu`-Dropdown gebündelt (analog zum bestehenden Rechtsklick-Kontextmenü), statt vier zusätzliche Einzelknöpfe zu belegen.

### 3. Realistischere Speicherplatz-Warnung vor Aufgabe 2/4

`_run_preflight_checks` nutzte für den Zielordner bisher eine feste 6-GB-Schwelle, unabhängig von der tatsächlichen Quellgröße. Bei sehr großen Spielen (100+ GB) kam die Warnung dadurch faktisch nie rechtzeitig. Neue Methode `_estimate_unpack_space_requirement`: liest über `mkpfs.pfs.inspect_pfs_image(..., verify_payloads=False)` nur Kopf- und Inode-Tabelle der `.ffpfsc`/`.ffpfs`-Datei (kein voller Entpackvorgang, unter 0,5 Sekunden auch bei 110 GB), ermittelt die logische Größe des inneren Images (`logical_file_bytes`) und nutzt das Doppelte davon als Schätzung – der reale Spitzenbedarf beim "FALL A"-Entpackmuster (Innenimage und bereits verschobene Dateien liegen kurzzeitig gleichzeitig vor).

## Bedeutung für Nutzer

- Vier zusätzliche, optionale Werkzeuge für fortgeschrittene PS5-Homebrew-Nutzung, ohne die Titelleiste zu überladen.
- Titelleiste ist bei Standardfenstergröße wieder vollständig nutzbar, Sprachumschalter wieder sichtbar.
- Bei sehr großen Spielen warnt die App jetzt zuverlässig vor Platzmangel, bevor der Vorgang mitten in der Verarbeitung fehlschlägt.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden.
- Alle vier neuen Fenster per Smoke-Test geöffnet (kein Absturz); Dropdown-Menü-Einträge einzeln per `.invoke()` ausgelöst und geprüft.
- AMPR-Index-Builder: Rundlauf-Test mit echtem Testordner, Header/Records/Pfade exakt verifiziert.
- Dump-Rename: Test mit drei Fällen (vollständige Daten/nur Titel-ID/keine Daten) bestätigt korrekte Ampel-Einstufung und tatsächliches Umbenennen.
- Speicherplatz-Schätzung: getestet an einer 486-MB- und einer 110-GB-Datei (Schätzung 0,47s, ~261 GB), Ergebnis plausibel.
- Alle 8 Hauptaufgaben (1-8) mit einer echten kleinen Testdatei end-to-end durchgetestet und bestätigt funktionsfähig, inklusive Aufgabe 5 (Sammelkonvertierung) mit zwei Quellen.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.24** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
