# PS5 Dump & Image Converter v1.8.4 – Release Notes

## Zweck dieses Releases

Version **v1.8.4** behebt vollständig einen Absturz, der beim automatischen Neustart nach einem Design-Wechsel in der gebauten `.exe` auftrat. Der in v1.8.3 vorgenommene erste Korrekturversuch war unvollständig. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Symptom

Nach Klick auf ANWENDEN im Design-Dialog erschienen zwei Fehlermeldungen, weiterhin auch nach dem v1.8.3-Fix:

1. „Unhandled exception in script … Can't find a usable init.tcl … This probably means that Tcl wasn't installed properly."
2. „Failed to remove temporary directory: …\AppData\Local\Temp\_MEI…"

## Ursache

Der automatische Neustart (`_restart_application`, seit v1.8.2) startet eine zweite Instanz der `.exe` per `subprocess.Popen`. Der PyInstaller-Onefile-Bootloader setzt beim Entpacken mehrere interne Umgebungsvariablen im eigenen Prozess:

- `_MEIPASS2` (Bootloader-intern)
- `TCL_LIBRARY` und `TK_LIBRARY` (gesetzt vom mitgelieferten Tk-Runtime-Hook `pyi_rth__tkinter.py`, jeweils auf `sys._MEIPASS + "_tcl_data"` bzw. `"_tk_data"` zeigend)

Alle drei zeigen auf den eigenen Temp-Extraktionsordner des jeweiligen Prozesses. `subprocess.Popen` vererbt standardmäßig die volle Umgebung des aufrufenden Prozesses. Der v1.8.3-Fix entfernte nur `_MEIPASS2` – `TCL_LIBRARY`/`TK_LIBRARY` blieben jedoch gesetzt und zeigten weiterhin auf den Temp-Ordner des Elternprozesses. Tcl liest `TCL_LIBRARY` beim Start vorrangig aus der Umgebung; der neu gestartete Prozess suchte seine Tcl/Tk-Laufzeit dadurch im falschen (und vom Elternprozess beim Beenden gleich gelöschten) Ordner, obwohl er selbst bereits korrekt und vollständig in einen eigenen, neuen Ordner entpackt hatte.

## Fix

`_restart_application` entfernt jetzt zusätzlich `TCL_LIBRARY` und `TK_LIBRARY` sowie – als generelle Absicherung gegen künftige PyInstaller-interne Variablen – alle mit `_MEI` beginnenden Umgebungsvariablen aus der an den Kindprozess übergebenen Umgebung:

```python
child_env = os.environ.copy()
for _stale_var in ("TCL_LIBRARY", "TK_LIBRARY"):
    child_env.pop(_stale_var, None)
for _stale_key in [k for k in child_env if k.startswith("_MEI")]:
    child_env.pop(_stale_key, None)
subprocess.Popen(args, close_fds=True, env=child_env)
```

## Verifikation

- Bundeter Programmcode (`PyInstaller.utils.cliutils.archive_viewer`) bestätigt: `_tcl_data`/`_tk_data` inklusive `init.tcl` sind korrekt in der `.exe` gebündelt – die Ursache lag ausschließlich in der vererbten Umgebung, nicht in einer fehlenden Ressource.
- Der PyInstaller-Runtime-Hook `pyi_rth__tkinter.py` wurde als Quelle für `TCL_LIBRARY`/`TK_LIBRARY` identifiziert und im Test exakt nachgebildet.
- Gezielter Test setzt `_MEIPASS2`, `TCL_LIBRARY` und `TK_LIBRARY` im eigenen Prozess (nach dessen eigenem, unabhängigem Tk-Start) und bestätigt, dass keine der drei Variablen an den simulierten Kindprozess weitergegeben wird.
- Der bereits bestehende Test für die Theme-Neustart-Logik läuft weiterhin erfolgreich.
- Syntax-Check, Release-Test-Gate und alle 77 Modultests weiterhin grün.
- Die EXE wurde mit dem vollständigen Fix neu gebaut: `dist\PS5_Dump_Image_Converter_v1.8.4.exe`.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.4 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.4.exe` (29,3 MB). `SOURCE_FILE_MANIFEST_v1.8.4.sha256` wurde nach dem Build neu erzeugt (95 Dateien).
