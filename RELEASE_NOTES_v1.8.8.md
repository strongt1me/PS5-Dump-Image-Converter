# PS5 Dump & Image Converter v1.8.8 – Release Notes

## Zweck dieses Releases

Version **v1.8.8** behebt einen Fehler beim wiederholten Design-Wechsel in der Windows-`.exe`: Nach einem erfolgreichen ersten Wechsel konnte der automatische Neustart beim zweiten Wechsel fehlschlagen. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Symptom

Beim ersten Wechsel des Design-Themas (DESIGN -> ANWENDEN) startete das Programm korrekt neu. Wurde danach ein weiteres Theme gewählt und erneut auf ANWENDEN geklickt, konnte der Neustart in manchen Umgebungen fehlschlagen und eine Fehlermeldung anzeigen.

## Ursache

Der Neustartpfad einer PyInstaller-Onefile-`.exe` muss sicherstellen, dass der Kindprozess als vollständig frische Instanz startet. In der Praxis kann ein teilweise geerbter Laufzeitkontext bei wiederholtem Self-Restart dazu führen, dass der zweite Neustart nicht mehr stabil initialisiert.

## Änderung

Die Neustartlogik in `_restart_application` wurde für wiederholte Neustarts gehärtet:

1. Im EXE-Modus wird `PYINSTALLER_RESET_ENVIRONMENT=1` gesetzt, damit PyInstaller den Kindprozess als vollständig frischen Onefile-Start behandelt.
2. Der Kindprozess startet mit stabilem Arbeitsverzeichnis (`cwd`):
   - `.exe`-Modus: Verzeichnis von `sys.executable`
   - Skript-Modus: Verzeichnis von `sys.argv[0]`
3. Die bereits vorhandene Bereinigung von `TCL_LIBRARY`, `TK_LIBRARY` und `_MEI*`-Variablen bleibt unverändert aktiv.

## Bedeutung für Nutzer

Der Design-Wechsel kann jetzt mehrfach hintereinander durchgeführt werden. Auch beim zweiten (und weiteren) Wechsel startet die Anwendung nach ANWENDEN zuverlässig im neu gewählten Theme neu.

## Verifikation

- Syntax-Check erfolgreich: `python -m py_compile PS5ImageConverter_Pro_FINAL_revised.py`
- Geänderte Datei ohne IDE-Fehler (Pylance/Problems-Ansicht).

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.8** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
