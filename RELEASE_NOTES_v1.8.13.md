# PS5 Dump & Image Converter v1.8.13 – Release Notes

## Zweck dieses Releases

Version **v1.8.13** behebt einen Fehler, durch den die Metadaten-Anzeige (Titel, Titel-ID, Version, Region usw.) für `.ffpfsc`-Dateien immer den langsamen, vollständigen Entpackvorgang durchlief statt des vorgesehenen schnellen, unpack-freien Lesepfads. Zusätzlich liest dieser schnelle Pfad jetzt auch verschachtelte PFS-in-PFS-Container direkt. Die übrige Konvertierungslogik ist unverändert.

## Ausgangslage

Für `.ffpfsc`-Dateien gab es bereits einen unpack-freien Lesepfad für die Metadaten-Anzeige, der nur bei Fehlschlag auf den vollständigen Entpackvorgang zurückfallen sollte. In der Praxis griff dieser schnelle Pfad jedoch nie: Beim Aufräumen des internen, virtuellen Datei-Handles wurde unbedingt eine `close()`-Methode aufgerufen, die dieses Handle gar nicht besitzt. Die dadurch ausgelöste Ausnahme trat in einem `finally`-Block auf, nachdem bereits ein erfolgreiches Ergebnis zur Rückgabe bereitstand – die Ausnahme ersetzte dieses Ergebnis, sodass die äußere Fehlerbehandlung es verwarf und immer der langsame, vollständige Entpackvorgang lief. Zusätzlich deckte der schnelle Pfad bisher nur `.ffpfsc`-Dateien ab, deren innerer Container ein eingebettetes exFAT-Image ist – nicht die von Aufgabe 1 (Dump-Ordner → `.ffpfsc`/`.ffpfs`) standardmäßig erzeugten, verschachtelten PFS-in-PFS-Container.

## Änderung

### Schneller Lesepfad repariert

Das Aufräumen des virtuellen Datei-Handles ruft `close()` jetzt nur noch auf, wenn die Methode tatsächlich existiert. Ein erfolgreich gefundenes Ergebnis wird dadurch nicht mehr verworfen.

### Verschachtelte PFS-Container werden jetzt direkt gelesen

Ein neuer, leichter Adapter (`_open_virtual_pfs_reader`) baut über die vorhandenen MkPFS-Kernfunktionen (Header, Inode-Tabelle, Superroot/Indizes, Verzeichnisbaum) einen schreibgeschützten Zugriff auf den inneren PFS-Container einer `.ffpfsc`-Datei, ohne etwas zu entpacken. Einzelne Dateien (`sce_sys/param.json`, `param.sfo`, `icon0.png`) werden erst bei Bedarf gezielt gelesen und bei Bedarf entpackt. Der bestehende, formatunabhängige Metadaten-Extraktor wird dabei unverändert wiederverwendet.

## Bedeutung für Nutzer

Die Titel-Info für `.ffpfsc`-Dateien erscheint jetzt spürbar schneller, besonders bei über Aufgabe 1 erzeugten Dateien. Am Inhalt der Anzeige ändert sich nichts.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (83 Tests, davon 2 neu) bestanden.
- GUI-Smoke-Test (echte Tkinter-Instanziierung) erfolgreich.
- Neuer, funktionaler Test (`test_ffpfsc_virtual_meta.py`): baut mit dem echten, vendorten MkPFS-Werkzeug einen realen, zweistufig verschachtelten `.ffpfsc`-Container (rohes inneres PFS → äußerer Container) und prüft, dass Titel-ID, Version und Region korrekt und über den schnellen Lesepfad (nicht den Unpack-Fallback) gelesen werden.
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.13** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
