# PS5 Dump & Image Converter v1.8.17 – Release Notes

## Zweck dieses Releases

Version **v1.8.17** behebt einen Anzeigefehler beim in v1.8.16 eingeführten Hintergrundbild: Es war bislang komplett unsichtbar. Die übrige Logik ist unverändert.

## Ausgangslage

Nach der Rückmeldung, dass das gewählte Hintergrundbild trotz erfolgreicher Übernahme (Meldung, gespeicherter Pfad) nirgendwo im Hauptfenster zu sehen war, wurde der Ursache nachgegangen: Sidebar und Hauptbereich sind jeweils komplett mit einer blickdichten Hintergrundfarbe gefüllte Bereiche. Das Hintergrundbild lag als eigenes Label ganz unten in der Z-Reihenfolge des Fensters – hinter diesen deckenden Bereichen war es unabhängig vom gewählten Bild oder der Deckkraft niemals zu sehen. Das betraf auch das zuvor immer fest eingebaute Standard-Hintergrundbild, das dadurch faktisch nie sichtbar war.

## Änderung

### Eigenes Hintergrundbild für den Hauptbereich

Der Hauptbereich (rund um Quelle, Zielformat, Zielordner, Temp-Ordner – der Bereich, der auch beim ursprünglichen Funktionswunsch gemeint war) bekommt jetzt ein eigenes, auf seine tatsächliche Größe skaliertes Hintergrundbild, das bei jeder Fenstergrößenänderung automatisch neu zugeschnitten wird. Die einzelnen Eingabefelder-Karten bleiben weiterhin gut lesbar und unverändert deckend.

## Bedeutung für Nutzer

Ein gewähltes (oder das eingebaute Standard-)Hintergrundbild ist jetzt tatsächlich sichtbar, nicht mehr nur in den Einstellungen gespeichert, aber unsichtbar.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (98 Tests) weiterhin bestanden.
- GUI-Smoke-Test um eine neue Prüfung erweitert: bestätigt, dass das Hintergrund-Label im Hauptbereich existiert, sichtbar ist, an unterster Z-Ebene liegt und nach Bildauswahl exakt auf die aktuelle Größe des Hauptbereichs skaliert wird.
- Zusätzliche manuelle Verifikation mit echten Bildschirmaufnahmen einer echten Tkinter-Instanz: ein Test-Hintergrundbild ist deutlich sichtbar hinter Überschrift, Zwischentiteln und rund um die Eingabefelder-Karte.
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.17** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
