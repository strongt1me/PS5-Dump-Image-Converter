# PS5 Dump & Image Converter v1.8.21 – Release Notes

## Zweck dieses Releases

Version **v1.8.21** entfernt die letzten verbliebenen bildlosen Kästen im Hauptfenster: Überschrift/Untertitel, die Statuszeile unten rechts und die Start/Abbrechen-Leiste (samt Fortschritts- und Größenanzeige) zeigten bisher noch eine deckende Kastenfarbe statt des Hintergrundbilds, obwohl Titelleiste, Sidebar und Content-Bereich es seit v1.8.20 bereits zeigten.

## Ausgangslage

`header_label`/`subtitle_label` (Überschrift "1. Dump-Ordner konvertieren" usw.) nutzen die ttk-Styles `Header.TLabel`/`Subtitle.TLabel`, `status_label` und `size_label` die Standard-`TLabel`-Vorlage – alle drei Styles setzen eine deckende Hintergrundfarbe (`background=c["bg_main"]"`), die jedes darunterliegende Hintergrundbild vollständig verdeckt. Die Start/Abbrechen-Leiste (`action_bar`) ist ein eigenständiger `tk.Frame` mit fester Hintergrundfarbe, ebenfalls ohne jede Bildspur.

## Änderung

### Bildausschnitt statt Kastenfarbe für Content-Beschriftungen

Nach demselben, bereits in v1.8.18 für QUELLE/ZIELFORMAT eingeführten Prinzip bekommen Überschrift, Untertitel, Statuszeile und Größenanzeige jetzt den zu ihrer Position passenden Ausschnitt des Content-Hintergrundbilds als eigenes Bild (`compound="center"`), statt eine sichtbare Kastenfarbe zu zeigen. Ein neuer, allgemeiner Helfer `_compute_content_bg_crop` berechnet diesen Ausschnitt anhand der Bildschirmposition des jeweiligen Labels relativ zum Content-Bereich – unabhängig davon, ob das Label direkt im Content-Bereich oder verschachtelt in der Start/Abbrechen-Leiste liegt. `_redraw_content_captions` zieht diese Beschriftungen bei jeder Größenänderung nach, nach demselben bewährten Cache-Verfahren wie bei den Karten-Beschriftungen (Textgröße wird nur bei tatsächlicher Textänderung neu vermessen, um kein Wackeln zu verursachen).

### Eigenes Hintergrundbild für die Start/Abbrechen-Leiste

Die Start/Abbrechen-Leiste bekommt zusätzlich ein eigenes Hintergrundbild-Label (`action_bar_bg_label`), analog zu Sidebar und Titelleiste aus v1.8.20, damit auch die leeren Flächen zwischen den Knöpfen das Bild zeigen.

## Bedeutung für Nutzer

Das Hintergrundbild ist jetzt tatsächlich im gesamten Hauptfenster sichtbar – keine dunklen Kästen mehr um Überschrift, Statuszeile, Größenanzeige oder die Start/Abbrechen-Leiste. Buttons und Eingabefelder bleiben unverändert auf ihrer eigenen, gut lesbaren Hintergrundfarbe.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden.
- Echte Tkinter-Screenshots bestätigen: Überschrift/Untertitel und die Start/Abbrechen-Leiste zeigen das Hintergrundbild statt eines Kastens; Widget-Zustand der Größenanzeige (Text und Bild) wurde zusätzlich direkt geprüft.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.21** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
