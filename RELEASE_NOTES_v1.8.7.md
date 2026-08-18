# PS5 Dump & Image Converter v1.8.7 – Release Notes

## Zweck dieses Releases

Version **v1.8.7** reduziert eine rein kosmetische Meldung, die beim automatischen Neustart nach einem Design-Wechsel gelegentlich weiterhin erscheint. Die Konvertierungslogik (Aufgaben 1–8) sowie die abgesicherte FFPKG-Kernlogik aus v1.7.90 sind **unverändert**.

## Symptom

Nach dem in v1.8.6 behobenen Absturz funktioniert der Design-Wechsel zuverlässig. Beim Beenden der alten Prozessinstanz erscheint jedoch gelegentlich folgende Warnung:

```text
Warning
Failed to remove temporary directory:
C:\Users\JBUSER~1\AppData\Local\Temp\_MEI109562
```

Wichtiger Unterschied zu allen vorherigen Meldungen: Dies ist eine reine `Warning` (gelbes Dreieck), kein `Unhandled exception`-Absturz (rotes Kreuz). Das Programm läuft danach normal weiter; der Design-Wechsel selbst war bereits erfolgreich.

## Ursache

Die alte Instanz versucht beim Beenden, ihren eigenen temporären Onefile-Entpackungsordner vollständig zu löschen. Ist zu diesem Zeitpunkt noch eine einzelne Datei darin gesperrt – am wahrscheinlichsten durch einen Echtzeit-Virenscan der zuvor ausgeführten Dateien – schlägt das Löschen fehl, und der PyInstaller-Bootloader zeigt diese Warnung. Der Ordner wird dadurch nicht sofort entfernt, belegt aber nur wenig Speicherplatz und wird typischerweise durch reguläre Temp-Bereinigung des Betriebssystems irgendwann entfernt.

Diese Meldung entsteht in der nativen Bootloader-Cleanup-Routine, die erst nach dem vollständigen Beenden des Python-Interpreters läuft – sie lässt sich aus Python-Code heraus nicht direkt abfangen oder unterdrücken.

## Änderung

Zwei Anpassungen in `_restart_application`, um die Wahrscheinlichkeit einer noch bestehenden Dateisperre zum Zeitpunkt des Aufräumens zu verringern:

1. Die Wartezeit zwischen dem Start der neuen Instanz und dem Beenden der alten wurde von 1,5 auf 2,5 Sekunden erhöht.
2. Vor dem Beenden ruft die alte Instanz `root.quit()` (sauberer Tcl-Interpreter-Stopp) vor `root.destroy()` auf und führt anschließend `gc.collect()` aus, um nicht mehr benötigte Objekte und damit verbundene native Handles gezielt freizugeben.

```python
try:
    self.root.quit()
except Exception:
    pass
self.root.destroy()
import gc
gc.collect()
sys.exit(0)
```

**Einordnung:** Diese Meldung ist im Gegensatz zu den in v1.8.4–v1.8.6 behobenen Fehlern nicht deterministisch reproduzierbar und hängt von externen Faktoren (insbesondere Sicherheitssoftware) ab, die außerhalb der Kontrolle der Anwendung liegen. Ein vollständiges Ausschließen ist daher nicht möglich; die Änderung reduziert lediglich die Wahrscheinlichkeit.

## Verifikation

- Bestehende Tests für die Neustart-Logik (Umgebungsbereinigung, Dialogverhalten) laufen weiterhin erfolgreich mit den angepassten Zeit-/Cleanup-Werten.
- Syntax-Check, Release-Test-Gate und alle 77 Modultests weiterhin grün.
- Die EXE wurde mit der Änderung neu gebaut: `dist\PS5_Dump_Image_Converter_v1.8.7.exe`.

## Vollständigkeit des Release

Versionsnummern wurden konsistent in `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`), `README.md`, `Start_Build.bat`, `Build_EXE.ps1`, `PS5ImageConverter_Pro.spec`, `file_version_info.txt` und `test_build_ready.py` auf v1.8.7 angehoben. Die EXE wurde erfolgreich gebaut: `dist\PS5_Dump_Image_Converter_v1.8.7.exe` (28,6 MB). `SOURCE_FILE_MANIFEST_v1.8.7.sha256` wurde nach dem Build neu erzeugt (101 Dateien).
