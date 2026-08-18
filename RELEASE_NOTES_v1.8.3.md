# PS5 Dump & Image Converter v1.8.3 – Release Notes

## Zweck dieses Releases

Version **v1.8.3** ist ein Bugfix-Release auf Basis von v1.8.2: Es behebt einen Absturz, der beim automatischen Neustart nach einem Design-Wechsel in der gebauten `.exe` auftrat. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Anlass

Nutzer-Rückmeldung direkt nach dem ersten Test der v1.8.2-`.exe`: Nach Klick auf ANWENDEN im Design-Dialog erschienen zwei Fehlermeldungen:

1. „Unhandled exception in script … Can't find a usable init.tcl … This probably means that Tcl wasn't installed properly."
2. „Failed to remove temporary directory: …\AppData\Local\Temp\_MEI196402"

## Ursache

Der in v1.8.2 eingeführte automatische Neustart (`_restart_application`) startete eine zweite Instanz der `.exe` per `subprocess.Popen`, ohne die geerbte Prozessumgebung zu bereinigen. Der PyInstaller-Onefile-Bootloader setzt beim Entpacken die interne Variable `_MEIPASS2` im eigenen Prozess-Environment, die auf seinen eigenen Temp-Extraktionsordner zeigt. Da `subprocess.Popen` standardmäßig die volle Umgebung des aufrufenden Prozesses vererbt, hielt sich der neu gestartete Kindprozess fälschlich für bereits entpackt und griff auf denselben `_MEI...`-Ordner zu wie der Elternprozess. Der Elternprozess löschte diesen Ordner jedoch unmittelbar danach beim Beenden (`sys.exit(0)`) – der Kindprozess fand daraufhin seine Tcl/Tk-Laufzeit nicht mehr, und der Elternprozess konnte seinen eigenen Temp-Ordner nicht vollständig entfernen, weil der Kindprozess noch Dateien darin offen hielt.

Dies ist ein bekanntes Verhalten bei PyInstaller-Onefile-Anwendungen, die sich selbst neu starten, und trat ausschließlich in der gebauten `.exe` auf (der Python-Skript-Modus kennt `_MEIPASS2` nicht und war nie betroffen).

## Fix

`_restart_application` entfernt `_MEIPASS2` jetzt explizit aus der Kopie der Umgebungsvariablen, die an den neu gestarteten Prozess übergeben wird:

```python
child_env = os.environ.copy()
child_env.pop("_MEIPASS2", None)
subprocess.Popen(args, close_fds=True, env=child_env)
```

Der Kindprozess entpackt sich dadurch unabhängig und vollständig in einen eigenen, neuen Temp-Ordner.

## Verifikation

- Neuer, gezielter Test simuliert exakt das gemeldete Szenario: `_MEIPASS2` wird im eigenen `os.environ` gesetzt (wie es der Onefile-Bootloader tun würde), `subprocess.Popen` wird abgefangen, und es wird geprüft, dass die an den Kindprozess übergebene Umgebung `_MEIPASS2` **nicht** mehr enthält, während das eigene `os.environ` unverändert bleibt.
- Der bereits bestehende Test für die Theme-Neustart-Logik (Klick auf ANWENDEN löst Neustart aus; bei laufender Aufgabe kein automatischer Neustart) läuft weiterhin erfolgreich.
- Syntax-Check, Release-Test-Gate und alle 77 Modultests weiterhin grün.
- Die EXE wurde mit dem Fix neu gebaut: `dist\PS5_Dump_Image_Converter_v1.8.3.exe`.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.3 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.3.exe` (29,3 MB). `SOURCE_FILE_MANIFEST_v1.8.3.sha256` wurde nach dem Build neu erzeugt (93 Dateien).
