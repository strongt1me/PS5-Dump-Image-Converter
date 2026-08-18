# PS5 Dump & Image Converter v1.8.2 – Release Notes

## Zweck dieses Releases

Version **v1.8.2** ist ein kleines Korrektur-Release auf Basis von v1.8.1: Der Design-Wechsel (DESIGN-Knopf) löst jetzt einen automatischen Neustart aus, damit die Benutzeroberfläche zuverlässig und vollständig im gewählten Farbschema erscheint. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Anlass

Nutzer-Rückmeldung: Beim Wechseln des Designs sollte ein Hinweis erscheinen, dass ein Neustart nötig ist, um die Oberfläche korrekt darzustellen – und ein Klick auf ANWENDEN sollte das Programm direkt neu starten. Hintergrund: Der in v1.8.1 eingeführte Live-Theme-Wechsel (`_apply_theme`/`_recolor_widget`) aktualisiert zwar das Hauptfenster und bereits offene Zusatzfenster, aber viele der zahlreichen Dialogfenster im Programm lesen die Farbpalette nur einmal beim Erstellen. Ohne Neustart blieben diese Fenster nach einem Theme-Wechsel teilweise im alten Design.

## Änderungen

| Bereich | Änderung |
| --- | --- |
| Design-Dialog | Neuer Hinweistext: „Nach dem Anwenden startet das Programm neu, damit die Benutzeroberfläche korrekt im neuen Design angezeigt wird." |
| ANWENDEN-Button | Speichert das gewählte Design und startet das Programm automatisch neu (`_restart_application`, funktioniert in `.exe`- und Skript-Modus gleichermaßen) |
| Laufende Aufgabe | Kein automatischer Neustart, falls gerade eine Konvertierung läuft (verhindert Abbruch); Design wird stattdessen live übernommen, mit Hinweis auf späteren manuellen Neustart |
| Dialoggröße | Von 300 auf 345 px Höhe erhöht, damit der neue Hinweistext nicht abgeschnitten wird |

## Verifikation

- Eigens geschriebener Test (`tools`-Verzeichnis-Stil, Headless-GUI mit `tkinter`) simuliert einen Theme-Wechsel über die echten Dialog-Widgets: bestätigt, dass ANWENDEN bei geändertem Theme `_restart_application()` auslöst und die Einstellung speichert.
- Zweiter Testfall bestätigt: Bei laufender Aufgabe (`is_running=True`) wird **kein** automatischer Neustart ausgelöst, stattdessen erscheint eine Warnung und das Design wird nur live angewendet.
- Syntax-Check, Release-Test-Gate (Syntax + 22 Build-Readiness- + 39 Code-Quality-Tests) und alle 77 Modultests weiterhin grün.

## Dokumentation

- `BENUTZERHANDBUCH.md`: Abschnitt „Design (Farbschema) wählen" aktualisiert – beschreibt jetzt den automatischen Neustart statt der vorherigen (nicht mehr zutreffenden) Live-Übernahme ohne Neustart.
- `CHANGELOG.md`: neuer Eintrag, Versionsübersicht ergänzt.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.2 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.2.exe` (29,3 MB). `SOURCE_FILE_MANIFEST_v1.8.2.sha256` wurde nach dem Build neu erzeugt (91 Dateien).
