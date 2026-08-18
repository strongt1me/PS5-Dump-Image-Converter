# PS5 Dump & Image Converter v1.8.27 – Release Notes

## Zweck dieses Releases

Version **v1.8.27** macht die AMPR-EMU-/PlayGo-Versionen und eine Auswahl an Hintergrundbildern zum festen Bestandteil des Programms: Beide Ordner liegen im Projekt und werden beim EXE-Bau eingebettet, sodass in Aufgabe 7 kein Versionsordner mehr ausgewählt werden muss und im Design-Dialog sofort Hintergrundbilder zur Verfügung stehen. Zusätzlich entfallen die Werkzeuge Y2JB und Dump umbenennen, und die Beschriftung des Aufgabenknopfes 7 ist korrigiert.

## Änderungen im Einzelnen

### 1. Mitgelieferte Ressourcen

Neue Modulfunktion `_bundled_resource()` löst Ressourcenpfade sowohl im Skriptbetrieb (Projektordner bzw. Ordner der ausführbaren Datei) als auch im gefrorenen Zustand (`sys._MEIPASS`) auf. Aufrufer müssen den Unterschied nicht kennen.

In `PS5ImageConverter_Pro.spec` werden zwei Ordner eingebettet, jeweils nur wenn vorhanden:

- `PlayGo & AMPR_EMU` – fünf AMPR-EMU-Versionen (0.2.6 bis 0.2.7.6) in je zwei Varianten sowie PlayGo v0.5 in zwei Varianten
- `Hintergrundbilder` – Auswahl für den Design-Dialog

### 2. Versionsordner in Aufgabe 7

`_ampr_resolve_store()` bestimmt den Versionsspeicher in fester Reihenfolge: ausdrückliche Angabe, gespeicherte eigene Auswahl, mitgelieferter Ordner. Damit funktioniert Aufgabe 7 ohne jede Vorbereitung, eine eigene Sammlung hat aber weiterhin Vorrang.

Betroffen sind alle Zugriffspunkte: der Aktionsteil der Engine, das Eingabefeld im Manager-Dialog, die Set-Übertragung im AMPR Picker und der Dateidialog für eigene Bibliotheken. Wird im Dialog wieder der mitgelieferte Ordner gewählt, wird bewusst nichts gespeichert, damit die automatische Auflösung erhalten bleibt.

In der Kommandozeile ist `--ampr-store` dadurch optional geworden; nur ohne mitgelieferten Ordner wird die Angabe weiterhin verlangt.

### 3. Hintergrundbilder

`_bundled_background_images()` listet die mitgelieferten Bilder (PNG, JPG, JPEG, BMP, GIF, WEBP, TIF, TIFF). Der Design-Dialog zeigt sie in einer Auswahlliste mit der Schaltfläche „Ausgewähltes übernehmen". Die bisherige Dateiauswahl für eigene Bilder bleibt unverändert und öffnet jetzt im mitgelieferten Ordner.

### 4. Getrennte Auswahl für AMPR und PlayGo

Der Manager-Dialog hatte zunächst ein gemeinsames Auswahlfeld für beide Bibliotheken. Damit ließ sich pro Durchgang immer nur eine von beiden setzen – für einen APR-Titel, der beide braucht, unbrauchbar. Jetzt hat jede Bibliothek ein eigenes Feld mit ihren eigenen Versionen, und die Engine wertet eine Auswahl je Bibliothek aus (`ampr_selection`) statt einer gemeinsamen Version für alle. Die globalen Filter `--ampr-version`/`--ampr-variant` bleiben unverändert nutzbar.

Vorausgewählt ist nur `libSceAmpr.sprx`: Das ist das eigentliche APR-EMU-Modul, das im Spielordner unter `fakelib/` ersetzt wird. `libScePlayGo.sprx` stammt aus dem separaten Projekt `pgo_stub` und meldet dem Spiel, dass alle PlayGo-Chunks bereits installiert sind – das wird erst gebraucht, wenn ein Titel Inhalte als nicht installiert behandelt. Entsprechend gilt beim Übernehmen und beim Übertragen über FTP jetzt `_AMPR_DEFAULT_APPLY_LIBS = ("libSceAmpr.sprx",)`; Wiederherstellen und Entfernen erfassen weiterhin beide Dateien. Der Knopf im Picker heißt dazu passend „APR-EMU übertragen".

### 5. Entfernte Werkzeuge

`_show_y2jb_install()` (224 Zeilen) und `_show_dump_rename_window()` (216 Zeilen) wurden samt Menüeinträgen, Regionstabelle, `dump_rename`-Import und 44 Übersetzungsschlüsseln entfernt. Im Menü „Weitere Tools" verbleiben MicroMount und der AMPR-Index-Builder.

Nicht betroffen: der **JS Loader**, der intern „Y2JB Remote JS Loader" heißt, die Credits-Nennung des Y2JB-Projekts sowie zwei Schlüssel (`y2jb.msg_invalid_port`, `y2jb.send_button`), die den Payload-Versand im MicroMount-Editor beschriften. Das Modul `ps5_validator/utils/dump_rename.py` bleibt samt Test im Projekt, nur ohne Oberflächenanbindung.

### 6. Beschriftung von Aufgabe 7

Bei der Umbenennung von `fakelib_manager` auf `ampr_manager` in v1.8.26 war der Übersetzungsschlüssel `mode.fakelib_manager` nicht mitgezogen worden; der Aufgabenknopf zeigte deshalb den Schlüsselnamen `mode.ampr_manager`. Der Schlüssel heißt jetzt `mode.ampr_manager` mit dem Text „7. AMPR EMU Manager", das Fallback-Label in `_MODE_OPTIONS` ist angeglichen.

### 7. JS Loader: Suchpfad für eigene Payloads

Die Schnellauswahl im JS Loader ermittelte den `helloworld`-Ordner über `os.path.dirname(os.path.abspath(__file__))`. In der gebauten EXE zeigt das ausschließlich in das entpackte Bündel; selbst abgelegte `.elf`-Dateien neben der EXE blieben unsichtbar. Der Ordner wird jetzt über `_bundled_resource()` aufgelöst, das Bündel und Programmordner prüft.

Der `helloworld`-Ordner war in allen bisherigen Fassungen leer – in keinem Manifest seit v1.7.90 ist eine Datei daraus verzeichnet. PyInstaller bettet leere Ordner nicht ein; das Build-Skript meldete das bisher trotzdem als „OK" und warnt jetzt stattdessen. Mit dieser Version enthält der Ordner 17 Payload-Dateien, die in die EXE eingebettet werden.

### 8. Einstellungen werden atomar gespeichert

`_save_setting()` öffnete die Konfigurationsdatei mit `open(..., "w")`, was sie sofort leert, und schrieb den Inhalt erst danach. Ein gleichzeitiger Lesezugriff erhielt dadurch eine leere oder halb geschriebene Datei – im Anwendungsprotokoll als `Expecting value: line 1 column 1` bzw. `Extra data: line 1 column 131` sichtbar. Ein Abbruch zwischen Leeren und Schreiben hätte sämtliche Einstellungen verworfen.

Geschrieben wird jetzt in eine temporäre Datei mit anschließendem `fsync` und `os.replace`; ein klassenweites Lock verhindert paralleles Lesen-Ändern-Schreiben aus mehreren Threads. Da `os.replace` unter Windows scheitert, solange ein anderer Zugriff die Zieldatei offen hält, wiederholen Schreiben (6 Versuche) und Lesen (4 Versuche) den Zugriff kurz, statt die Einstellung zu verwerfen.

Nachgewiesen mit vier parallelen Schreiber-Threads und einem dauerhaft lesenden Thread: 2855 Lesevorgänge über `_load_setting()`, kein einziger falscher Rückgabewert, Konfiguration am Ende gültig und vollständig.

### 9. Wiederhergestellte Übersetzungstabelle

Beim Entfernen der Schlüssel wurde `ps5_validator/utils/i18n.py` beschädigt: Ein Skript löschte bei mehrzeiligen Einträgen nur die Schlüsselzeile, ein Reparaturversuch entfernte anschließend auch intakte Einträge. Die Datei wurde aus dem Bytecode-Cache (`__pycache__/i18n.cpython-314.pyc`, 1164 Schlüssel) neu erzeugt, um die 44 zu entfernenden bereinigt und um die seither ergänzten Schlüssel sowie die Konstante `ZSTD_LEVEL_KEYS` vervollständigt. Eine vollständige Gegenprüfung bestätigt, dass alle 966 im Code verwendeten Schlüssel vorhanden sind.

## Bedeutung für Nutzer

- Aufgabe 7 ist ohne Vorbereitung einsatzbereit – die AMPR-Versionen sind dabei.
- Hintergrundbilder lassen sich direkt auswählen, ohne eine Datei zu suchen.
- Beides gilt auch für die Windows-EXE, ohne zusätzliche Ordner daneben.
- Das Menü „Weitere Tools" ist auf die beiden verbliebenen Werkzeuge reduziert.

## Verifikation

- Versionsspeicher: mitgelieferter Ordner wird gefunden, alle 12 Einträge (10× AMPR, 2× PlayGo) korrekt eingelesen und sortiert.
- Auflösungsreihenfolge geprüft: ausdrückliche Angabe gewinnt, ein ungültiger Pfad fällt auf den mitgelieferten Ordner zurück.
- Aufgabe 7 **ohne** `--ampr-store` an einem echten Dump-Ordner: „v0.2.7.6 (no debug)" und „v0.5 (nolog)" übernommen, `ampr_emu.index` mit 193 Dateien neu gebaut, Exit 0.
- Hintergrundbilder: Ordner und enthaltenes Bild werden erkannt.
- Getrennte Auswahl geprüft: AMPR 0.2.6 (debug) und PlayGo 0.5 (log) gleichzeitig übernommen, beide per SHA-256 gegen die Quelle bestätigt; anschließend nur PlayGo gewechselt, AMPR blieb unverändert.
- Standardumfang geprüft: ohne Angabe wird ausschließlich `libSceAmpr.sprx` übernommen, PlayGo erst auf ausdrückliche Anforderung; Entfernen erfasst beide.
- Übersetzungsschlüssel: alle 966 verwendeten Schlüssel vorhanden, keine Reste der entfernten Werkzeuge.
- JS Loader: Ordnerauflösung mit Testdatei geprüft (Datei neben dem Programm wird gefunden); 17 Payload-Dateien im Archiv der gebauten EXE nachgewiesen.
- Aufgabenknöpfe: alle acht zeigen ihren Namen, keiner einen Schlüsselnamen; in Deutsch und Englisch geprüft.
- `test_all_quality_new.py`: 14/14. `test_ffpkg_production_integration.py`, `test_i18n.py`, `test_build_ready.py`, `test_exfat_folder_build.py`, `test_param_json_recovery.py`, `test_dump_rename.py`, `test_background_image.py`: alle bestanden.

Die Einbettung wurde im Archiv der fertigen EXE nachgewiesen: 12 `.sprx`-Dateien, das Hintergrundbild und die Payload-Dateien sind enthalten.

**Noch offen:** Dass das laufende Programm die eingebetteten Ordner zur Laufzeit auflöst, zeigt sich erst beim Start der EXE.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.27** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.27.sha256`
