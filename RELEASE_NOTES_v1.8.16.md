# PS5 Dump & Image Converter v1.8.16 – Release Notes

## Zweck dieses Releases

Version **v1.8.16** bringt einen neuen Knopf **EINSTELLUNGEN** in der Titelleiste: Dort lässt sich ein eigenes Hintergrundbild für das Hauptfenster wählen, das automatisch in das passende Format umgewandelt und mit fester Deckkraft angezeigt wird. Die übrige Konvertierungslogik ist unverändert.

## Ausgangslage

Das Programm zeigte bisher immer ein fest eingebautes Hintergrundbild im Hauptfenster (unveränderlich, ohne Auswahlmöglichkeit). Es gab weder einen zentralen Ort für Programmeinstellungen jenseits der Design-/Sprachauswahl noch eine Möglichkeit, dieses Hintergrundbild durch ein eigenes zu ersetzen.

## Änderung

### Neuer EINSTELLUNGEN-Knopf

In der Titelleiste (neben DESIGN) öffnet ein neuer Knopf einen Einstellungen-Dialog mit dem Bereich „Hintergrundbild“.

### Eigenes Hintergrundbild, automatisch konvertiert

Über „Bild wählen…“ akzeptiert der Dialog jedes von Pillow lesbare Bildformat (JPG, PNG, BMP, GIF, WEBP, TIFF u. a., auch mit Alphakanal) und wandelt es intern automatisch in das benötigte Format um – unabhängig vom Ausgangsformat. Das gewählte Bild wird mit der Design-Hintergrundfarbe auf 30 % Deckkraft geblendet (dezenter Wasserzeichen-Effekt, damit Bedienelemente und Text gut lesbar bleiben) und wirkt sofort, ohne Neustart. Die Wahl wird dauerhaft gespeichert und bleibt auch nach einem Neustart des Programms erhalten. „Zurücksetzen“ stellt jederzeit wieder den ursprünglichen Standard-Hintergrund her.

## Bedeutung für Nutzer

Das Hauptfenster lässt sich jetzt individuell mit einem eigenen Bild gestalten, ohne sich um Format oder Größe kümmern zu müssen – das Programm übernimmt die Umwandlung automatisch.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py ps5_validator/utils/i18n.py`
- Vollständige Testsuite (98 Tests, davon 6 neu) bestanden.
- GUI-Smoke-Test (echte Tkinter-Instanziierung) erfolgreich.
- Zusätzlicher Live-Durchlauf mit einer echten Tkinter-Instanz: Knopf sichtbar und korrekt beschriftet, Dialog öffnet bildschirmzentriert, Bildauswahl wird sofort im Hauptfenster übernommen, Einstellung wird korrekt gespeichert.
- Neue, gezielte Tests: Blend-Berechnung nutzt exakt die konfigurierte Deckkraft, verschiedene Bildformate (PNG mit Alphakanal, BMP) werden korrekt nach RGB umgewandelt, ungültige Dateien werden abgewiesen statt zum Absturz zu führen, ein gespeicherter eigener Pfad hat Vorrang vor dem Standardbild, ein nicht mehr vorhandener gespeicherter Pfad fällt sauber auf den Standard zurück.
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.16** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
