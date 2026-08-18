# PS5 Dump & Image Converter v1.8.22 – Release Notes

## Zweck dieses Releases

Version **v1.8.22** bündelt eine größere Überarbeitung der Oberfläche: modernisierte Zusatzfenster, ein größeres/abgerundetes Hauptfenster-Layout, ein feinjustiertes Hintergrundbild-System (inkl. eines neuen, unabhängigen Sidebar-Hintergrundbilds), DPI-bewusste scharfe Darstellung bei Windows-Skalierung über 100 % sowie mehrere in diesem Zuge gefundene und behobene Detailfehler.

## Änderungen im Einzelnen

### 1. Modernisierung der Zusatzfenster

Diagnose, KLog, Bibliothek, ShadowMount+, Param/Manifest-Editor, PKG-Merger, Design und Einstellungen wurden auf ein einheitliches, moderneres Erscheinungsbild umgestellt (native Windows-Titelleiste, konsistente Kopfzeile mit Titel/Untertitel über neue Helfer `_build_modern_toplevel`/`_build_modern_header`). Der FileZilla-Client und das Credits-Fenster wurden bewusst unverändert gelassen.

Zusätzlich wurde ein Regressionsfehler behoben: Durch die DPI-Awareness (siehe Punkt 4) wurden Schriften bei Windows-Skalierung über 100 % größer gerendert als die bisherigen, fest kodierten Fenstermaße vorsahen – dadurch waren in den Fenstern Design und Einstellungen die untersten Knöpfe nicht mehr erreichbar. Beide Fenster nutzen jetzt den bestehenden Helfer `_build_scrollable_body` (Canvas + Scrollbar), sind größenveränderbar (`resizable=True`, mit sinnvoller Mindestgröße) statt fest, und bleiben dadurch bei jeder Skalierung vollständig bedienbar.

### 2. Hauptfenster-Layout

Start- und Abbrechen-Knopf sowie die drei Ordner-Auswahl-Knöpfe (Quelle, Ziel, Temp) wurden von `ttk.Button` auf die eigene `RoundedButton`-Klasse umgestellt: größer, abgerundet, mit eigener Deaktiviert-Optik (`state`, `disabledbackground`, `disabledforeground` wurden dafür neu in `RoundedButton` ergänzt). Die Quelle-Karte hat mehr Innenabstand, Eingabefelder und ihre Schrift wurden vergrößert, und ein neuer borderloser Style (`PathCard.TFrame`) entfernt eine zuvor sichtbare Rahmennaht um die Quelle-Karte.

### 3. Hintergrundbild-System

- Verbleibende schmale, bildlose Ränder in Sidebar, Content-Bereich und Quelle-Karte wurden entfernt. Ursache war ein Tk-Verhalten, bei dem `place(relwidth=1, relheight=1)` auf einem Kind eines gepolsterten Frames (`padx`/`pady`/`padding`) sich auf die innere Fläche des Elternelements bezieht statt auf dessen volle Größe – behoben durch kompensierende Offsets (`x=-P, y=-P, width=+2P, height=+2P`).
- Die Werkzeugleiste (Diagnose/KLog/Bibliothek/ShadowMount+/Param/Manifest/PKG-Merger) zeigt auf ausdrücklichen Wunsch bewusst **kein** Hintergrundbild mehr; das zugehörige Titelleisten-Hintergrundbild-Label wurde vollständig entfernt.
- Neu: ein eigenes, unabhängig auswählbares Hintergrundbild nur für die Sidebar (Aufgaben-Knöpfe 1–8, Spielvorschau), über eine neue Sektion im Einstellungen-Fenster wählbar und separat zurücksetzbar. Es hat standardmäßig kein Bild (kein eingebetteter Default) und wird – wie das Hauptbild – automatisch skaliert, sanft eingefärbt und geschärft.
- Ein Fehler im Live-Design-Wechsel (Theme-Wechsel ohne Neustart, nur während ein Task läuft) wurde behoben: `_apply_theme()` lud das Hintergrundbild bislang nicht neu und aktualisierte auch nicht die Textfarben der Karten-Beschriftungen, wodurch Mittel-/Hell-Design nach einem Live-Wechsel streckenweise kaum lesbar war. Beide werden jetzt korrekt mit aktualisiert.

### 4. DPI-Awareness

Die App meldet sich beim Start jetzt als Per-Monitor-v2-DPI-bewusst (`SetProcessDpiAwareness(2)`, mit Fallback auf `SetProcessDPIAware()`). Dadurch wird die Oberfläche bei Windows-Bildschirmskalierung über 100 % scharf gerendert statt von Windows nachträglich hochskaliert und dadurch unscharf/verpixelt dargestellt.

## Bedeutung für Nutzer

- Die Zusatzfenster wirken aufgeräumter und einheitlicher; in Design und Einstellungen sind jetzt garantiert alle Knöpfe erreichbar, notfalls per Scrollen.
- Hauptfenster-Bedienelemente sind größer, runder und leichter zu treffen.
- Das Hintergrundbild deckt Sidebar, Content-Bereich und Quelle-Karte lückenlos ab; die Werkzeugleiste bleibt bewusst bildfrei, damit die Knöpfe dort klar hervortreten.
- Die Sidebar kann jetzt ein eigenes Hintergrundbild bekommen, unabhängig vom Hauptbereich.
- Bei höherer Windows-Bildschirmskalierung wirkt die App insgesamt schärfer.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Vollständige Testsuite bestanden.
- Echte Tkinter-Screenshots sowie direkte Widget-/Größenprüfungen (`winfo_width`, `find_all`, Pixel-Sampling) bestätigten die einzelnen Fixes; für Design/Einstellungen wurde die Scrollbarkeit zusätzlich durch erzwungen zu kleine Fenstergrößen gegengeprüft.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.22** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
