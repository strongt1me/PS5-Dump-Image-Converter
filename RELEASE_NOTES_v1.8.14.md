# PS5 Dump & Image Converter v1.8.14 – Release Notes

## Zweck dieses Releases

Version **v1.8.14** baut auf dem in v1.8.13 reparierten schnellen `.ffpfsc`-Metadaten-Lesepfad auf: Er wird bei sehr großen Titeln nochmal deutlich schneller, und `.exfat`/`.ffpkg` werden jetzt vor dem Bau auf eine gültige `sce_sys/param.json` geprüft. Die übrige Konvertierungslogik ist unverändert.

## Ausgangslage

Bei einer Prüfung mit echten, großen `.ffpfsc`-Dateien (bis 148 GB) fiel auf, dass der in v1.8.13 reparierte schnelle Lesepfad zwar überall griff, bei sehr dateireichen Titeln aber deutlich langsamer war als bei ähnlich großen, aber dateiärmeren Titeln (16,7 s statt unter 1 s bei einem 109-GB-Titel). Grund: Die Dateisuche durchlief immer den kompletten Verzeichnisbaum des Containers, auch nachdem `param.json`, `param.sfo` und `icon0.png` längst gefunden waren.

Außerdem wurde bei einer 1:1-Prüfung des `.exfat`-Bauwegs gegen Referenz-Tooling festgestellt, dass zwar der `.exfat`-Bauweg bereits vor dem Bau prüft, ob `sce_sys/param.json` in der Quelle vorhanden und gültig ist (seit v1.8.13), der `.ffpkg`-Bauweg diese Prüfung aber noch nicht hatte – dort konnte weiterhin eine Datei entstehen, die die PS5 anschließend mit "Missing/invalid param.json" ablehnt.

## Änderung

### Schnellerer Lesepfad bei dateireichen Titeln

Die Dateisuche für `.ffpfsc`-Metadaten bricht jetzt ab, sobald `param.json`, `param.sfo` und `icon0.png` gefunden wurden, statt den restlichen Verzeichnisbaum weiter einzulesen. Bei einem realen 109-GB-Titel mit besonders vielen Dateien sank die Ladezeit dadurch von 16,7 s auf 2,5 s.

### `.ffpkg`-Bau prüft jetzt ebenfalls `param.json` vorab

`_build_ffpkg_from_folder` bricht jetzt – wie der `.exfat`-Bauweg seit v1.8.13 – sofort mit einer klaren Meldung ab, wenn `sce_sys/param.json` in der Quelle fehlt oder kein gültiges JSON ist, statt Zeit in den Bau einer Datei zu investieren, die die PS5 ohnehin ablehnt.

## Bedeutung für Nutzer

Titel-Infos laden jetzt durchgängig schnell, unabhängig von der Dateizahl im Titel. Ein unvollständiger Quellordner (fehlende/beschädigte `param.json`) wird jetzt bei `.exfat` **und** `.ffpkg` sofort erkannt und gemeldet, statt erst auf der PS5 aufzufallen.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py ps5_validator/utils/i18n.py`
- Vollständige Testsuite (86 Tests) bestanden.
- GUI-Smoke-Test (echte Tkinter-Instanziierung) erfolgreich.
- Reale Verifikation mit 5 echten `.ffpfsc`-Dateien des Nutzers (0,5–148 GB): Metadaten-Lesepfad greift in allen Fällen, Geschwindigkeitsgewinn beim dateireichsten Titel direkt nachgemessen (16,7 s → 2,5 s).
- Quality-Testsuite (14 Prüfungen) bestanden.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.14** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
