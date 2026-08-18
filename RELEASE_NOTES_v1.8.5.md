# PS5 Dump & Image Converter v1.8.5 – Release Notes

## Zweck dieses Releases

Version **v1.8.5** behebt einen Absturz der Windows-`.exe` direkt beim Programmstart. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Symptom

Beim Start der `.exe` erschien folgender Fehler, bevor überhaupt ein Fenster sichtbar wurde:

```text
Traceback (most recent call last):
  File "tkinterdnd2\TkinterDnD.py", line 74, in _require
_tkinter.TclError: can't find package tkdnd

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "PS5ImageConverter_Pro_FINAL_revised.py", line 23793, in <module>
  File "tkinterdnd2\TkinterDnD.py", line 324, in __init__
  File "tkinterdnd2\TkinterDnD.py", line 76, in _require
RuntimeError: Unable to load tkdnd library.
```

## Ursache

`PS5ImageConverter_Pro.spec` sammelte die Dateien der optionalen Drag-&-Drop-Bibliothek `tkinterdnd2` zusätzlich über einen generischen `collect_data_files('tkinterdnd2')`-Aufruf ein. Dieser Aufruf unterscheidet nicht nach Zielplattform und sammelt die `tkdnd`-Unterordner aller unterstützten Systeme (Windows, Linux, macOS) unterschiedslos als reine "Daten" ein. Das kollidierte mit dem eigentlich korrekten, von `_pyinstaller_hooks_contrib` mitgelieferten Hook für `tkinterdnd2`, der plattformspezifisch nur den passenden Ordner samt nativer Bibliotheksdatei (`.dll`/`.so`/`.dylib`) einsammelt.

Prüfung des Archivinhalts der gebauten `.exe` (`PyInstaller.utils.cliutils.archive_viewer`) bestätigte: Die Ordner `tkinterdnd2/tkdnd/linux-*` und vermutlich `osx-*` waren vorhanden, der komplette `tkinterdnd2/tkdnd/win-x64`-Ordner fehlte vollständig – obwohl lokal auf dem Build-System vorhanden. Bei PyInstallers interner "Binär- vs. Daten"-Neuklassifizierung ging die für Windows benötigte `tkdnd`-DLL durch den zusätzlichen, undifferenzierten `collect_data_files`-Aufruf verloren.

Dieser Fehler bestand unabhängig vom in v1.8.2–v1.8.4 behandelten Neustart-Mechanismus und wäre bei jedem Start der `.exe` aufgetreten (nicht nur nach einem Design-Wechsel) – er blieb zuvor unbemerkt, weil ausschließlich der Python-Skript-Modus (mit lokal vollständig installiertem `tkinterdnd2`) wiederholt getestet worden war.

## Fix

Der zusätzliche Block in `PS5ImageConverter_Pro.spec`:

```python
try:
    from PyInstaller.utils.hooks import collect_data_files
    _datas += collect_data_files('tkinterdnd2')
except Exception:
    pass
```

wurde vollständig entfernt. `tkinterdnd2` steht bereits in der `hiddenimports`-Liste, wodurch PyInstaller automatisch den korrekten, mitgelieferten Community-Hook (`hook-tkinterdnd2.py`) anwendet – ohne manuelle Zusatzsammlung.

## Verifikation

- Archivinhalt der neu gebauten `.exe` geprüft: `tkinterdnd2/tkdnd/win-x64/` (DLL + `.tcl`-Dateien) ist jetzt korrekt enthalten.
- Syntax-Check, Release-Test-Gate und alle 77 Modultests weiterhin grün.
- Die EXE wurde mit dem Fix neu gebaut: `dist\PS5_Dump_Image_Converter_v1.8.5.exe`.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.5 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.5.exe` (28,6 MB – kleiner als v1.8.4, da die zuvor fälschlich mitgebündelten Linux-/macOS-Anteile von `tkinterdnd2` entfallen). `SOURCE_FILE_MANIFEST_v1.8.5.sha256` wurde nach dem Build neu erzeugt (97 Dateien).
