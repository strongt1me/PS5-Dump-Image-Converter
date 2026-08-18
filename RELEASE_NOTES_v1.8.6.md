# PS5 Dump & Image Converter v1.8.6 – Release Notes

## Zweck dieses Releases

Version **v1.8.6** härtet den automatischen Neustart nach einem Design-Wechsel (Design-Dialog → ANWENDEN) gegen eine sporadische Race Condition zwischen zwei kurzzeitig überlappenden Prozessinstanzen in der gebauten `.exe` ab. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Symptom

Nach dem in v1.8.5 behobenen `tkinterdnd2`-Bündelungsfehler trat beim Design-Wechsel sporadisch ein weiterer, deutlich selteneren Fehler auf:

```text
_tkinter.TclError: couldn't read file "C:/Users/JBUSER~1/AppData/Local/Temp/_MEI116962/_tcl_data/auto.tcl": no such file or directory

Traceback (most recent call last):
  File "PS5ImageConverter_Pro_FINAL_revised.py", line 23793, in <module>
  File "tkinterdnd2\TkinterDnD.py", line 323, in __init__
  File "tkinter\__init__.py", line 2345, in __init__
```

Wichtiger Unterschied zu den vorherigen Fehlern (v1.8.3/v1.8.4): Der Temp-Ordner (`_MEI116962`) in der Fehlermeldung gehörte diesmal korrekt zum **neuen, gerade gestarteten Prozess selbst** – nicht zu einem geerbten, bereits gelöschten Pfad einer anderen Instanz. Die Umgebungsvariablen-Fixes aus v1.8.4 griffen also wie vorgesehen.

## Ursache

Die Datei `auto.tcl` ist nachweislich vollständig im Programmarchiv enthalten (Dateianzahl im Archiv stimmt exakt mit einer vollständigen Tcl-8.6-Installation überein). Der Fehler trat dennoch auf, weil zwei PyInstaller-Onefile-Prozesse zeitlich zu dicht aufeinander folgten: Der automatische Neustart startet die neue Instanz und beendet die alte praktisch unmittelbar danach. Beide Instanzen entpacken bzw. entfernen dabei jeweils einen kompletten eigenen Temp-Ordner mit mehreren hundert Dateien. Läuft das Entpacken der neuen Instanz zeitlich zu dicht am Aufräumen der alten (z. B. durch Systemlast oder Echtzeit-Virenscan neu geschriebener Dateien), kann das Lesen einzelner, gerade erst geschriebener Dateien der neuen Instanz sporadisch fehlschlagen – unabhängig davon, dass die Datei im Archiv korrekt vorhanden ist.

## Fix

`_restart_application` wurde um zwei Maßnahmen ergänzt:

1. Der neue Prozess wird mit `DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP` gestartet und dadurch vollständig von Konsole und Prozessgruppe der alten Instanz gelöst.
2. Die alte Instanz wartet nach dem Start der neuen 1,5 Sekunden und prüft währenddessen, ob der neue Prozess unerwartet mit einem Fehlercode beendet wurde (`proc.poll()`/`proc.returncode`), bevor sie sich selbst schließt. Das gibt der neuen Instanz Zeit, ihre eigene Onefile-Entpackung vollständig abzuschließen, bevor die alte Instanz ihren eigenen Temp-Ordner entfernt.

```python
creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
proc = subprocess.Popen(args, close_fds=True, env=child_env, creationflags=creationflags)
time.sleep(1.5)
if proc.poll() is not None and proc.returncode != 0:
    raise RuntimeError(f"Neue Instanz wurde sofort mit Fehlercode {proc.returncode} beendet.")
```

**Einordnung:** Diese Fehlerklasse ist ihrer Natur nach eine zeitabhängige Race Condition, keine deterministische, zu 100 % reproduzierbare Ursache wie die vorherigen beiden Fehler (fehlende DLL-Bündelung, vererbte Umgebungsvariablen). Die Wartezeit reduziert das Zeitfenster für die Überschneidung erheblich, kann eine erneute, sehr seltene Überschneidung auf einem stark ausgelasteten oder von Sicherheitssoftware verlangsamten System aber nicht mit letzter Sicherheit ausschließen.

## Verifikation

- Neuer/aktualisierter Test bestätigt: Der Kindprozess wird mit den erwarteten `creationflags` gestartet, die bereinigte Umgebung bleibt unverändert korrekt, und der Rückgabewert des (simulierten) Kindprozesses wird nach der Wartezeit geprüft.
- Der bereits bestehende Test für die Theme-Neustart-Dialoglogik läuft weiterhin erfolgreich.
- Syntax-Check, Release-Test-Gate und alle 77 Modultests weiterhin grün.
- Die EXE wurde mit dem Fix neu gebaut: `dist\PS5_Dump_Image_Converter_v1.8.6.exe`.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.6 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.6.exe` (28,6 MB). `SOURCE_FILE_MANIFEST_v1.8.6.sha256` wurde nach dem Build neu erzeugt (99 Dateien).
