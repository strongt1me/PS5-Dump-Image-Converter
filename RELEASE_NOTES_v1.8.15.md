# PS5 Dump & Image Converter v1.8.15 – Release Notes

## Zweck dieses Releases

Version **v1.8.15** ersetzt den harten Abbruch bei fehlender oder beschädigter `sce_sys/param.json` (eingeführt in v1.8.13/v1.8.14) durch ein Angebot: Statt den Bau von `.exfat`, `.ffpkg`, `.ffpfsc` und `.ffpfs` nur zu verweigern, fragt das Programm per Ja/Nein, ob automatisch eine gültige param.json erstellt werden soll. Die übrige Konvertierungslogik ist unverändert.

## Ausgangslage

Seit v1.8.13/v1.8.14 bricht der Bau von `.exfat` und `.ffpkg` ab, wenn `sce_sys/param.json` in der Quelle fehlt oder ungültig ist – das verhindert, dass die PS5 das Ergebnis später mit „Missing/invalid param.json“ ablehnt. Nutzer, die aus Versehen genau diese Datei aus ihrem Spiel gelöscht haben, standen damit aber vor einer Sackgasse: Der einzige Ausweg war ein komplett neues Backup vom Original. Für `.ffpfsc`/`.ffpfs` (Aufgabe 1) gab es die Vorprüfung bisher noch gar nicht.

## Änderung

### Ja/Nein-Angebot statt Abbruch

Wird `sce_sys/param.json` als fehlend oder ungültig erkannt, erscheint jetzt eine Abfrage mit der nach Möglichkeit aus dem Datei-/Ordnernamen erkannten Titel-ID (z. B. `PPSA04263`). Bei Zustimmung wird eine minimale, gültige param.json direkt in `sce_sys/` geschrieben und der Bau läuft normal weiter. Bei Ablehnung bricht der Bau wie zuvor mit einer klaren Meldung ab.

### Für alle vier Formate

Die gleiche Vorprüfung und dasselbe Angebot gelten jetzt konsistent für `.exfat`, `.ffpkg` **und** `.ffpfsc`/`.ffpfs` (Aufgabe 1), nicht mehr nur für `.exfat`/`.ffpkg`.

### Wiederverwendete Bausteine

Für die Erstellung wird das bereits vorhandene, geprüfte param.json-Grundgerüst aus dem Param-/Manifest-Editor-Modul genutzt (`create_default_param`/`save_param_json`), keine neue, parallele Logik. Die Titel-ID-Erkennung nutzt dieselbe Musterprüfung wie der bestehende `.ffpkg`-Metadaten-Fallback (jetzt in eine gemeinsame Konstante ausgelagert, damit beide Stellen synchron bleiben).

## Bedeutung für Nutzer

Eine versehentlich gelöschte oder beschädigte param.json ist kein Grund mehr für ein komplett neues Backup – ein Klick auf „Ja“ genügt, sofern die Titel-ID nicht anderweitig bekannt sein muss. Wird keine Titel-ID im Namen erkannt, entsteht trotzdem eine gültige, aber generische param.json (es wird nie eine Titel-ID erfunden).

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py ps5_validator/utils/i18n.py`
- Vollständige Testsuite (92 Tests, davon 4 neu) bestanden.
- GUI-Smoke-Test (echte Tkinter-Instanziierung) erfolgreich.
- Neue, gezielte Tests: Titel-ID-Erkennung aus Namen, `.exfat`-Bau bei Ja/Nein-Antwort (inkl. byte-genauem Rundlauf des neu erstellten Ergebnisses), `.ffpfsc`/`.ffpfs`-Vorprüfung (Bau erreicht die Pack-Engine nur nach „Ja“, nie nach „Nein“).
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.15** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
