# PS5 Dump & Image Converter v1.8.20 – Release Notes

## Zweck dieses Releases

Version **v1.8.20** macht das Hintergrundbild auch in der Titelleiste und der Sidebar sichtbar. Bisher zeigte nur der Content-Bereich (rechts, rund um QUELLE/ZIELFORMAT usw.) das Bild – Titelleiste (oben) und Sidebar (links) blieben durchgehend deckende, bildlose Flächen.

## Ausgangslage

Titelleiste (`_main_titlebar`) und Sidebar hatten von Anfang an eine eigene, vollständig deckende Hintergrundfarbe (`header_bg` bzw. `bg_main`) ohne eigenes Hintergrundbild-Label. Der Vollbild-Hintergrund im Hauptfenster (`self.bg_label`) liegt zwar hinter dem gesamten Fenster, wird aber von diesen beiden durchgehend deckenden Bereichen komplett verdeckt – genau wie es beim Content-Bereich vor v1.8.17 der Fall war. Für Nutzer wirkte das wie ein dicker, bildloser Rahmen oben und links im Fenster.

## Änderung

### Eigene Hintergrundbild-Labels für Titelleiste und Sidebar

Nach demselben Muster wie beim Content-Bereich (`content_bg_label`) bekommen Titelleiste und Sidebar jetzt jeweils ein eigenes `tk.Label` an unterster Z-Ebene, das auf die eigene Größe skaliert wird und bei Größenänderung des Fensters entkoppelt vom `<Configure>`-Event nachgezogen wird (`_on_titlebar_configure`/`_apply_titlebar_bg_resize` und `_on_sidebar_configure`/`_apply_sidebar_bg_resize`). Buttons, Nav-Einträge und Beschriftungen behalten ihre eigene, deckende Hintergrundfarbe für gute Lesbarkeit – nur die leeren Flächen dazwischen zeigen jetzt das Bild statt eines einheitlichen Farbtons. `_refresh_bg_label()` (z. B. beim Wechsel des eigenen Hintergrundbilds in den Einstellungen) aktualisiert beide neuen Labels mit.

## Bedeutung für Nutzer

Das Hintergrundbild (Standard oder selbst gewähltes) ist jetzt im gesamten Hauptfenster sichtbar statt nur im rechten Content-Bereich. Das Protokollfenster (Konsole) bleibt weiterhin bewusst deckend mit nur einer dezenten Farbtönung, da dort tatsächlich Text mitläuft.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden, inkl. `test_background_image.py`.
- Echter Tkinter-Screenshot der laufenden App bestätigt: Bild sichtbar in Titelleiste, Sidebar und Content-Bereich, keine bildlosen Streifen mehr außerhalb der bewusst deckenden Konsole.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.20** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
