# PS5 Dump & Image Converter v1.8.25 – Release Notes

## Zweck dieses Releases

Version **v1.8.25** ist ein reines Fehlerbehebungs-Release. Es korrigiert einen Fehler, durch den Aufgabe 7 bei `.ffpfsc`- und `.ffpfs`-Quellen unbrauchbare Dateien erzeugte, schärft die Abschlussprüfung so nach, dass ein solches Ergebnis nicht mehr als Erfolg durchgeht, macht Aufgabe 7 im Kommandozeilenmodus nutzbar und behebt vier weitere Fehler bei Rechteprüfung, Temp-Bereinigung, englischer Spracheinstellung und Protokollbeschriftung.

## Änderungen im Einzelnen

### 1. Aufgabe 7: dreifache Verschachtelung bei .ffpfsc/.ffpfs

`_repack_nested_ffpfsc()` (in `_mode_fakelib_manager`) baute das innere PFS ohne das mkpfs-Flag `--raw`. Ohne dieses Flag legt die vendorte MkPFS-Bibliothek von sich aus eine weitere Image-Ebene an, sodass das Ergebnis dreifach statt zweifach verschachtelt war – derselbe Fehler, der für Aufgabe 1 bereits in v1.8.10 behoben wurde, dort aber nicht auf diesen Pfad übertragen worden war.

Sichtbar wurde das im Protokoll: `pack folder --no-compress` meldete `Total files: 1 / Compressed files: 1` statt `Total files: 193 / Uncompressed files: 193`. Beim Zurückentpacken der erzeugten Datei kam eine einzelne 626-MB-Containerdatei heraus statt der 193 Dump-Dateien.

Behoben durch Ergänzen von `--raw`. Zusätzlich folgt der äußere Container jetzt der Zielendung: eine `.ffpfs`-Datei wird mit `--no-compress` geschrieben, statt trotz Endung immer komprimiert zu werden.

Nicht betroffen waren Dump-Ordner-, `.exFAT`- und `.ffpkg`-Quellen – diese nutzen eigene Erzeugungspfade (`_create_exfat_from_folder`, `_build_ffpkg_from_folder`).

### 2. Abschlussprüfung erkennt fehlende Dump-Struktur

`_verify_output_artifact()` prüfte bei Ordner-Ergebnissen nur `count > 0 and total > 0`. Ein Zielordner mit einer einzigen, großen, unbrauchbaren Datei galt damit als erfolgreich. Bei Zielformat "Dump-Ordner" wird jetzt zusätzlich `eboot.bin` oder `sce_sys/param.json` verlangt – direkt im Ordner oder in einem seiner Unterordner, damit Sammelziele aus Aufgabe 5 weiterhin bestehen. Für Datei-Ziele und für Modi ohne Zielformat-Auswahl (Aufgabe 7 im Ordnerbetrieb, Aufgabe 8) gilt die bisherige Regel unverändert.

Dabei fiel auf, dass der Statustext "Abschlussprüfung erfolgreich" **vor** der Prüfung gesetzt wurde und bei einem Fehlschlag stehen blieb. Die Reihenfolge ist jetzt umgekehrt, mit eigenem Status für den Fehlerfall.

### 3. Aufgabe 7 im Kommandozeilenmodus

`_mode_fakelib_manager` öffnet ohne Automations-Angabe einen modalen Auswahldialog. Im `--cli`-Modus gibt es kein sichtbares Fenster, der Aufruf wartete deshalb endlos. `_run_cli()` befüllt jetzt den bereits vorhandenen Automations-Hook `_fakelib_automation_spec` über neue Argumente:

`--fakelib-action` (`fakelib_add`, `fakelib_replace`, `fakelib_remove`, `files_add`, `dirs_add`, `files_remove`), `--fakelib-src`, `--fakelib-files`, `--fakelib-dirs`, `--fakelib-items`, `--fakelib-apr`, `--ampr-emu-folder`.

Fehlt `--fakelib-action` bei Aufgabe 7, bricht der Aufruf mit Rückgabewert 2 und einer Auflistung der gültigen Werte ab. Werden `--fakelib-*`-Argumente bei einer anderen Aufgabe übergeben, wird das ebenfalls abgewiesen.

### 4. Rechteprüfung vor dem FFPKG-Bau

`_build_ffpkg_from_folder()` besaß keinen Preflight. Ohne erhöhte Rechte probierte es alle drei UFS2-Profile nacheinander durch, die jeweils mit `[WinError 740]` abbrachen. Jetzt prüft die Methode die Rechte vorab und meldet den Grund im Klartext – analog zum bereits vorhandenen Preflight im Lesepfad `_extract_ffpkg_via_ufs2tool`. Bewusst ohne Dokan-Prüfung: `newfs`/`makefs` schreiben ein Image und mounten nichts; die spätere Dateizahl-Prüfung überspringt sich bereits selbst, wenn Dokan fehlt.

### 5. Temp-Bereinigung bei schreibgeschützten Dateien

Aus einer `.ffpkg` extrahierte Dateien tragen das ReadOnly-Attribut aus dem Image. `shutil.rmtree(..., ignore_errors=True)` scheitert daran mit `[WinError 5]` und ließ den kompletten Ordner still liegen – bei einem Game-Dump mehrere hundert Megabyte pro Durchlauf. Neue Modulfunktion `_rmtree_force()` setzt das Attribut im Fehlerfall zurück und wiederholt den Löschvorgang; alle 30 `shutil.rmtree`-Aufrufe laufen jetzt darüber. Das Verhalten von `ignore_errors=False` (Ausnahme weiterreichen) bleibt erhalten.

### 6. Zielformat und Rückgabewert bei englischer Spracheinstellung

`_run_cli()` setzte das Zielformat über das deutsche Klassen-Label `_FORMAT_LABELS`, während `_format_label_to_key()` es über `self._t()` zurückliest. Bei englischer Einstellung liefen `--format folder` und `--format ffpfs` dadurch ins Leere (die übrigen drei Formate sind sprachneutral geschrieben). Jetzt wird das übersetzte Label gesetzt.

Beim Beheben zeigte sich, dass `_completion_status_text()` als einzige Statusfunktion noch hartkodiertes Deutsch enthielt; sie ist jetzt über 14 neue Übersetzungsschlüssel angebunden. Daraus folgte ein weiterer Fehler: `_run_cli()` leitete seinen Rückgabewert aus dem Statustext ab (`"fehler" in text.lower()`) und hätte mit übersetzten Meldungen **jeden fehlgeschlagenen Lauf bei englischer Einstellung als Erfolg gemeldet**. Die Auswertung hängt jetzt an einem Ergebnisflag, das `_write_task_report()` an jedem Aufgabenende setzt.

### 7. Aufgabennummern in Protokollmeldungen

Interne Konvertierungsschritte trugen feste Aufgabennummern, obwohl dieselbe Routine aus mehreren Aufgaben heraus aufgerufen wird. Ein Lauf von Aufgabe 4 protokollierte dadurch `>>> Aufgabe 6 – ffpkg zu ffpfsc`, ein Lauf von Aufgabe 6 zeigte `Aufgabe 3` und `Aufgabe 5`. Die Nummern wurden aus fünf Übersetzungstexten, vier `task_label`-Werten und den veralteten Meldungen der internen Quellprüfung entfernt; die tatsächlich laufende Aufgabe steht weiterhin in der Kopfzeile des Protokolls. `Aufgabe 7 – FFPKG neu packen` behält seine Nummer, da dieser Pfad nur einen Aufrufer hat.

## Bedeutung für Nutzer

- Mit Aufgabe 7 bearbeitete `.ffpfsc`/`.ffpfs`-Dateien sind wieder auf der Konsole verwendbar. Dateien, die mit einer früheren Version über diesen Weg erzeugt wurden, sollten neu erstellt werden.
- Ein unbrauchbares Ergebnis wird als Fehler gemeldet, statt als Erfolg durchzugehen.
- Aufgabe 7 ist skriptfähig; der `--cli`-Modus deckt jetzt tatsächlich alle acht Aufgaben ab.
- Fehlende Administratorrechte werden sofort und verständlich gemeldet statt nach drei Fehlversuchen mit einer Windows-Fehlernummer.
- Das Temp-Verzeichnis läuft nicht mehr voll.
- Die englische Oberfläche ist im Kommandozeilenmodus vollständig nutzbar.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py ps5_validator/utils/i18n.py`
- `test_all_quality_new.py`: 14/14 bestanden, erweitert um vier neue Prüfungen (`--raw` vorhanden, Außencontainer folgt der Endung, Ordner ohne Dump wird abgelehnt, echter Dump und Sammelziel werden akzeptiert).
- `test_ffpkg_production_integration.py`, `test_i18n.py`, `test_build_ready.py`, `test_exfat_folder_build.py`, `test_param_json_recovery.py`, `test_ffpfsc_virtual_meta.py`: alle bestanden.
- Aufgabe 7 nach dem Fix mit allen vier Quelltypen an echten Spieldaten geprüft: Dump-Ordner (in-place), `.ffpfsc`, `.ffpfs` (unkomprimiert bestätigt), `.exFAT` (65 Dateien), `.ffpkg` (193 Dateien, `fsck rc=0`).
- Rückentpackung der reparierten `.ffpfsc`: 193 Dateien / 648.840.389 Bytes mit vollständiger Dump-Struktur inklusive der zwei ergänzten `fakelib`-Dateien – exakt die Ausgangsgröße plus deren Umfang.
- Gegenprobe mit einer vor dem Fix erzeugten Datei: Abschlussprüfung schlägt an, Rückgabewert 1.
- Regressionsläufe an echten Spieldaten: Aufgabe 1 → `.ffpfsc`/`.ffpkg`, Aufgabe 2 → Dump-Ordner, Aufgabe 4 → Dump-Ordner, Aufgabe 5 (Sammelkonvertierung, 254 Dateien), Aufgabe 8 auf `.ffpkg` – alle unverändert erfolgreich.
- Temp-Bereinigung: direkter Vergleich an einem Baum mit schreibgeschützten Dateien (alt: bleibt vollständig liegen, neu: restlos entfernt) sowie am echten Fall nach Aufgabe 7 mit `.ffpkg`-Quelle (vorher 618 MB Rest, jetzt keiner).
- Englische Spracheinstellung: `--format folder` und `--format ffpfs` erzeugen die erwartete Ausgabe; Rückgabewert 0 im Erfolgs- und 1 im Fehlerfall bestätigt.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.25** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.25.sha256`
