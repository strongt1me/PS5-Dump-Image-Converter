# PS5 Dump & Image Converter v1.8.26 – Release Notes

## Zweck dieses Releases

Version **v1.8.26** ersetzt Aufgabe 7 vollständig: Aus dem fakelib Manager wird der **AMPR EMU Manager**. Er verwaltet AMPR-EMU- und PlayGo-Versionen, hält `ampr_emu.index` automatisch aktuell und kann über den neuen **AMPR Picker** direkt auf einer angeschlossenen PS5 arbeiten – Bibliotheken austauschen und den Index dort neu bauen, ohne ein Spiel-Image neu zu erstellen. Zusätzlich findet das Programm eine FileZilla-Installation jetzt unabhängig vom Installationsort.

## Änderungen im Einzelnen

### 1. Aufgabe 7: neuer Modus `ampr_manager`

Der Modusschlüssel `fakelib_manager` heißt jetzt `ampr_manager`, die Oberfläche zeigt „7. AMPR EMU Manager". Die früheren Datei-Aktionen (`fakelib_add`, `fakelib_replace`, `fakelib_remove`, `files_add`, `dirs_add`, `files_remove`) sind ersatzlos entfallen. Die Quelltypen bleiben unverändert: Dump-Ordner, `.ffpfsc`/`.ffpfs`, `.exFAT` und `.ffpkg`; die geprüfte Entpack- und Neupack-Kette einschließlich des `--raw`-Aufbaus aus v1.8.25 wird weiterverwendet.

### 2. Versionsverwaltung

`_ampr_scan_version_store()` liest einen frei wählbaren Ordner rekursiv nach `libSceAmpr.sprx` und `libScePlayGo.sprx` ein. Version und Variante werden aus dem Ablagepfad abgeleitet, wobei sowohl `0.2.7.6 debug` (Version im eigenen Ordnernamen) als auch `PlayGo_v0.5/log` (Version eine Ebene höher) erkannt werden. Sortiert wird numerisch nach Version, nicht alphabetisch – `0.2.7.6` steht damit korrekt vor `0.2.6`.

`_ampr_identify_installed()` bestimmt über SHA-256, welche Version in einem Dump steckt, und meldet unbekannte Dateien mit Größe und Prüfsumme statt sie zu verschweigen.

`_ampr_apply_library()` sichert die vom Spiel mitgelieferte Datei beim ersten Austausch als `<name>.orig`. Eine bereits vorhandene Sicherung wird nie überschrieben – andernfalls ginge das Original beim zweiten Wechsel verloren. `_ampr_restore_library()` holt sie zurück und entfernt die Sicherung, `_ampr_remove_library()` löscht Bibliothek und Sicherung.

### 3. Index

Nach jedem Eingriff wird `ampr_emu.index` über den bereits vorhandenen AMPRIDX3-Writer neu gebaut (abschaltbar über `--ampr-no-index`). Die Formatlogik wurde in `_ampr_write_index()` herausgezogen, sodass der lokale Scan und der FTP-Scan dieselbe Implementierung verwenden.

### 4. AMPR Picker und FTP-Betrieb

Neu portiert aus `ui/build_ampr_index.py` des ps5-exfat-builder 4.0.2: rekursiver Scan eines `/app0`-Verzeichnisses über FTP mit MLSD und NLST-Fallback, Index-Erzeugung und atomarer Upload (`STOR` auf `.tmp`, dann `rename`).

Ergänzt wurden:

- `_show_ampr_ftp_picker()` – Browser für die Spielordner der Konsole mit Schnellzugriffen auf `/data/etaHEN/games`, `/data/homebrew`, `/mnt/data`, `/user/app` und `/mnt/usb0`.
- `_ampr_ftp_validate_app0()` – prüft vor dem Indexieren auf `eboot.bin` und `sce_sys`, damit der Index nicht über einen beliebigen Ordner gebaut wird.
- `_ampr_ftp_apply_set()` – überträgt AMPR- und PlayGo-Bibliothek als Paar; APR-Titel benötigen beide.
- `_ampr_ftp_ensure_dir()` – legt einen fehlenden `fakelib`-Ordner an. Ohne diesen Schritt scheitert `STOR` bei Spielen ohne AMPR-Unterstützung mit `550 No such file or directory`.
- Automatische Portwahl: 2121, 1337 und 21 werden der Reihe nach probiert, der verwendete Port wird protokolliert.

### 5. FileZilla-Erkennung

Die Suche läuft jetzt fünfstufig: gespeicherter Pfad, Registry-`Install_Dir`, bekannte Installationspfade (um die Variante ohne Namenszusatz erweitert), **Windows-Deinstallationseinträge** und – als letzter Ausweg – ein zeitlich begrenzter Dateisystem-Durchlauf über die Programm- und Laufwerkswurzeln. Ein gefundener Pfad wird gespeichert, sodass die lange Suche höchstens einmal läuft.

Behoben wurde außerdem, dass ein leerer `Install_Dir`-Eintrag aus einer früheren Deinstallation zu `os.path.join("", "filezilla.exe")` führte – einem relativen Pfad, der im Arbeitsverzeichnis gesucht wurde.

### 6. Kommandozeile

Die `--fakelib-*`-Argumente wurden durch `--ampr-*` ersetzt: `--ampr-action` (`ampr_apply`, `ampr_restore`, `ampr_remove`, `ampr_index`, `ampr_ftp_index`), `--ampr-store`, `--ampr-version`, `--ampr-variant`, `--ampr-lib`, `--ampr-source`, `--ampr-no-backup`, `--ampr-no-index` sowie `--ampr-host`, `--ampr-port`, `--ampr-remote-path` und `--ampr-no-upload`. `ampr_ftp_index` arbeitet ausschließlich auf der Konsole und wird vor der `--source`-Prüfung abgezweigt.

## Bedeutung für Nutzer

- AMPR-Versionen lassen sich auswählen, wechseln und zurücksetzen, ohne Dateien von Hand zu kopieren.
- Die installierte Version wird benannt, statt nur als vorhandene Datei angezeigt zu werden.
- Ein Spiel auf der Konsole kann ohne Neubau des Images auf eine andere AMPR-Version umgestellt werden.
- Der Index passt nach jedem Eingriff wieder zum Dateibestand.
- FileZilla wird auch an ungewöhnlichen Installationsorten gefunden.

## Verifikation

Alle Prüfungen gegen echte Daten und eine echte Konsole (192.168.1.94, `ftpsrv.elf` auf Port 2121):

- Versions-Scan: 12 Einträge erkannt (5 AMPR-Versionen × 2 Varianten, PlayGo × 2), Sortierung und Variantenreihenfolge korrekt.
- Anwenden, Erkennen, Wiederherstellen, Entfernen an einem Dump-Ordner: Sicherung wird angelegt, bleibt beim zweiten Wechsel unverändert, Original kehrt zurück, Index folgt jeweils (193 → 194 → 193 → 191 Dateien).
- Container-Weg `.ffpfsc`: entpacken, AMPR anwenden, Index bauen, mit `pack folder --raw` neu packen – Exit 0.
- FTP-Index gegen einen simulierten Server: identische Pfade wie beim lokalen Scan, gleicher Header (`AMPRIDX3`, Version 3, 16 Slots).
- FTP gegen die echte PS5: Ordnerprüfung unterscheidet Spielverzeichnisse korrekt von ShadowMount-Stubs (`/user/app/PPSA19015` enthält nur `mount.lnk`); Index über 191 Dateien erzeugt und übertragen, lokale und übertragene Datei identisch (24.560 Bytes), keine `.tmp`-Reste.
- Hot-Swap gegen die echte PS5: `fakelib` angelegt, `libSceAmpr.sprx` v0.2.7.6 (no debug, 230.742 B) und `libScePlayGo.sprx` v0.5 (nolog, 14.390 B) übertragen, beide größengleich zur Quelle; Index danach 193 Einträge inklusive `/app0/fakelib/libSceAmpr.sprx` und `/app0/fakelib/libScePlayGo.sprx`.
- FileZilla: Standardinstallation über die Pfadliste (0,00 s) und über die Deinstallationseinträge gefunden; eine Testkopie unter `C:\PS5_Werkzeuge\FileZilla_manuell` wurde vom Scan in 0,6 s gefunden.
- `test_all_quality_new.py`: 14/14 bestanden. `test_ffpkg_production_integration.py`, `test_i18n.py`, `test_build_ready.py`, `test_exfat_folder_build.py`: alle bestanden. Zwei Tests wurden auf die neuen Namen umgestellt.

**Noch offen:** Ob ein auf diesem Weg vorbereitetes Spiel auf der Konsole tatsächlich startet, ist nicht geprüft – das lässt sich nur am Gerät feststellen.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.26** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.26.sha256`
