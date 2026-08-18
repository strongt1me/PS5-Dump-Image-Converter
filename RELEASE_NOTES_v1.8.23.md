# PS5 Dump & Image Converter v1.8.23 – Release Notes

## Zweck dieses Releases

Version **v1.8.23** ist ein kleines Folge-Release zu v1.8.22: Der Rückfrage-Dialog beim Startup-Cleanup entfällt zugunsten einer vollautomatischen Bereinigung, und ein optischer Fehler im neuen Sidebar-Hintergrundbild-Feature (grauer Kasten hinter dem Logo-Bereich) wurde behoben.

## Änderungen im Einzelnen

### 1. Automatische Bereinigung alter Temp-Dateien

Bisher fragte die App beim Start per `messagebox.askyesno` nach, ob gefundene alte, verwaiste PS5Conv-Temp-Artefakte (Standard: älter als 24h) gelöscht werden sollen. Diese Rückfrage entfällt: `_run_startup_temp_cleanup_scan` übergibt gefundene Kandidaten jetzt direkt an die neue Methode `_auto_cleanup_startup_temp`, die – wie zuvor der bestätigte Ja-Pfad – die Löschung in einem Hintergrund-Thread über die bestehende `_cleanup_startup_temp_candidates` durchführt, inklusive Protokolleinträgen und Statuszeilen-Meldung. Der Schutz "nicht löschen, während ein Task läuft" (`self.is_running`-Check mit Wiedervorlage nach 5s) bleibt erhalten. Die dadurch verwaisten, nur für den Dialogtext genutzten i18n-Schlüssel (`dialog.title.old_temp_files_found`, `dialog.msg.old_temp_files_found`, `dialog.msg.old_temp_files_run_clause`) wurden entfernt.

### 2. Sidebar-Logo-Bereich: grauer Kasten behoben

Die drei Beschriftungen im Sidebar-Logo-Bereich ("✕ ○ □ △", "PS5 DUMP", "& IMAGE CONVERTER") waren einfache `tk.Label`-Widgets mit fest deckender Hintergrundfarbe (`bg_main`) – anders als die bereits in v1.8.21 auf Bildausschnitt-statt-Kastenfarbe umgestellten Header-/Untertitel-Beschriftungen im Content-Bereich. Bei aktivem, eigenem Sidebar-Hintergrundbild (seit v1.8.22 wählbar) erschien dadurch ein deckender grauer Balken hinter dem Logo, unabhängig vom gewählten Design.

Diese drei Labels sind jetzt in `_sidebar_caption_labels` registriert und werden über die neuen Methoden `_compute_sidebar_bg_crop`/`_redraw_sidebar_captions` (analog zu `_compute_content_bg_crop`/`_redraw_content_captions`) mit dem zu ihrer Position passenden Ausschnitt des Sidebar-Hintergrundbilds als `compound="center"`-Bild versehen, statt einer sichtbaren Kastenfarbe. Zusätzlich wurde der Standard-Rahmen der Labels (`borderwidth=2`, `padx=1`, `pady=1` – Tk-Vorgabewerte) auf 0 gesetzt, da dieser sonst als dünner grauer Rand um Symbole/Text stehen geblieben wäre. `_redraw_sidebar_captions()` wird beim Sidebar-Resize, beim Setzen/Zurücksetzen des Sidebar-Hintergrundbilds und bei Sprachwechsel neu aufgerufen, exakt nach demselben Cache-Verfahren wie die bereits bestehenden Karten-/Content-Beschriftungen (Textgröße wird nur bei tatsächlicher Textänderung neu vermessen, um kein Wackeln zu verursachen).

## Bedeutung für Nutzer

- Beim Programmstart erscheint keine Rückfrage mehr wegen alter Temp-Dateien – sie werden automatisch entfernt.
- Der Sidebar-Logo-Bereich zeigt bei gewähltem Sidebar-Hintergrundbild jetzt in allen Designs lückenlos das Bild, ohne grauen Kasten oder Rahmen.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite (103 Tests) weiterhin bestanden.
- Echter Tkinter-Screenshot mit einem künstlichen Testbild (kräftiger Farbverlauf) bestätigt: Der Verlauf läuft jetzt nahtlos durch Icon-Zeile, "PS5 DUMP" und "& IMAGE CONVERTER", kein Kasten/Rand mehr sichtbar.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.23** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
