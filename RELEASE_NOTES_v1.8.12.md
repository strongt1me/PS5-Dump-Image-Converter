# PS5 Dump & Image Converter v1.8.12 – Release Notes

## Zweck dieses Releases

Version **v1.8.12** übersetzt die Benutzeroberfläche vollständig ins Englische und entfernt sieben nicht mehr über die Oberfläche erreichbare Werkzeuge. Die Konvertierungslogik selbst ist unverändert.

## Ausgangslage

Der **DE/EN**-Button in der Titelleiste existierte bereits, übersetzte aber nur ein kleines Grundgerüst: die acht Aufgaben-Namen in der Seitenleiste, STARTEN/ABBRECHEN und die übrigen Titelleisten-Buttons. Alle Dialoge, Nebenfenster und Protokollmeldungen blieben deutsch, auch im englischen Modus.

## Änderung

### Übersetzungsarchitektur

`ps5_validator/utils/i18n.py` wurde von einem kleinen, direkt textbasierten Übersetzungs-Dict auf eine stabile Schlüssel-Architektur umgestellt: Jeder Text bekommt einen sprachunabhängigen Schlüssel (z. B. `main.source_label`) statt des deutschen Textes selbst als Schlüssel. `translate(language, key, **kwargs)` liefert den passenden Text und formatiert dynamische Inhalte (Pfade, Zahlen, Dateinamen) über `str.format`. Insgesamt enthält die Datei jetzt 960 Übersetzungsschlüssel.

### Vollständig übersetzt

- Hauptfenster (Seitenleiste, Aufgaben-Auswahl, Quelle/Ziel/Temp, Kompressionsstufen, Statuszeile)
- Alle Dialoge, Bestätigungsabfragen und Fehlermeldungen
- Alle Nebenfenster: Credits, Ressourcen, Dokan2-Installer, JS Loader, Klog, ShadowMount+-Konfigurationseditor, Spiel-Info-Popup (inkl. Update-/Patch-Suche), fakelib Manager, PKG-Merger, Param-/Manifest-Editor, Bibliothek, Diagnosebericht (inkl. Berichtstext), Design-Auswahl und der FTP/SFTP-Client (das größte Nebenfenster mit rund 1800 Zeilen)
- Sämtliche Protokollmeldungen während einer laufenden Konvertierung (rund 400 Meldungen) sowie die Konsolenausgabe von JS Loader und FTP/SFTP-Client

Bewusst unübersetzt bleiben rein technische, nicht sprachliche Inhalte: reine Trennlinien im Protokoll, durchgereichte Ausgabe externer Prozesse (z. B. robocopy-Zeilen), Schlüssel-Wert-Rohdumps sowie zwei Startmeldungen zur MIT-Lizenz-Registrierung, die vor der Oberflächen-Initialisierung laufen.

### Entfernt: sieben nicht mehr erreichbare Werkzeuge

Bei der Übersetzungsarbeit fiel auf, dass folgende Fenster-Funktionen über keinen Knopf oder Menüeintrag der Oberfläche mehr aufrufbar waren: PKG-Inspektor, GP5-Projektdatei-Dialog, Dump Rename, PS5-Game-Manager, FPKG-Builder, DPI-Installer und der MicroMount-Konfigurationseditor. Der zugehörige Code (rund 1177 Zeilen) sowie die zugehörigen Abschnitte in README.md und BENUTZERHANDBUCH.md wurden entfernt.

## Bedeutung für Nutzer

Wer die Oberfläche auf Englisch nutzt, sieht jetzt durchgängig englischen Text – keinen Sprachmix mehr zwischen Oberfläche und Protokoll. Die Sprachwahl wird weiterhin pro Benutzer gespeichert. Am Funktionsumfang der acht Aufgaben und der verbleibenden Werkzeuge ändert sich nichts.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py ps5_validator/utils/i18n.py`
- Vollständige Testsuite (81 Tests) bestanden.
- GUI-Smoke-Test (echte Tkinter-Instanziierung) erfolgreich.
- Eigens erstellter End-to-End-Test für den Sprachumschalter (Haupt-Widgets Deutsch → Englisch → Deutsch, inkl. Kompressionsstufen-Persistenz) erfolgreich.
- Nach Entfernung der sieben toten Fenster-Funktionen: keine verbleibenden Referenzen auf die entfernten Funktions-/Konstantennamen im Quelltext.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.12** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
