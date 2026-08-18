# PS5 Dump & Image Converter v1.8.44 – Release Notes

## Zweck dieses Releases

Eine einzige Ursache, zwei sichtbare Fehler – gefunden über eine Bildschirmaufnahme einer laufenden Konvertierung.

---

## Was zu sehen war

Im Protokollfeld standen Zeilen wie diese:

```
Writing PFS image to E:\PS5_Temp\ps5conv_nested_pfs_y5m0fego\pfs_image.dat...[###------]  72% write @ 106.28 MB/s
Uncompressed size:   248.85 MB (260,935,330 bytes)[############----]  49% compress @ 11.71 MB/s
```

Meldung und Fortschrittsbalken kleben in **einer** Zeile. Und direkt darüber stapelten sich Balken, die sich hätten ersetzen sollen:

```
[##############################-]  99% write @ 101.31 MB/s ETA 0s
[##############################-]  99% write @ 101.27 MB/s ETA 0s
[###############################] 100% write @ 101.25 MB/s
```

---

## Die Ursache

Der Leser der Engine-Ausgabe suchte in seinem Puffer **erst nach `\n`, dann nach `\r`**:

```python
for sep in ("\n", "\r"):        # so nicht
    idx = self._buf.find(sep)
```

Die Engine schreibt aber gemischt: erst eine Meldung ohne Zeilenumbruch, dann mit `\r` den sich überschreibenden Balken. Kommt beides in einem Block an – `Writing PFS image to ...\r[####] 72% write\n` –, findet die Schleife zuerst das `\n` am Ende und nimmt **alles davor** als eine Zeile, mit dem `\r` mittendrin.

Daraus folgt auch das Stapeln: Eine so verklebte Zeile beginnt mit `Writing PFS image…`, nicht mit `[`. Sie gilt damit nicht als Fortschrittszeile, der Merker „die letzte war ein Balken" wird zurückgesetzt, und die nächste echte Balkenzeile wird **angehängt statt zu ersetzen**. Weil die Engine ständig Text und Balken mischt, passierte das laufend.

Die Zusammenfassung der Balkenzeilen aus v1.8.43 war also richtig gebaut – sie konnte nur nicht greifen, solange die Zeilen verklebt ankamen.

---

## Behoben

Getrennt wird jetzt am **zuerst** auftretenden Zeilenende, gleich welcher Art:

```python
stellen = [i for i in (self._buf.find("\n"), self._buf.find("\r")) if i >= 0]
idx = min(stellen)
```

Dazu drei Absicherungen:

- Kommen doch einmal zwei Balken in einer Zeile an, zählt nur der letzte.
- Die Phasenbezeichnung (`scan`, `read`, `write`, `compress`) wird mitgeführt. Balken **derselben** Phase ersetzen einander; bei einem Wechsel bleibt die abgeschlossene Zeile als Beleg stehen.
- Beide Schreibwege ins Protokollfeld führen denselben Zustand, sonst entstünde beim Übergang eine doppelte Zeile.

An einer echten Konvertierung nachgemessen (Dump-Ordner nach `.ffpfsc`, 249 MB):

| | vorher | nachher |
| --- | --- | --- |
| verklebte Zeilen | mehrere je Lauf | **0** |
| Balkenzeilen im Feld | hunderte | **1 bis 4** (eine je Phase) |

---

## Tests

Neu ist `test_protokollfeld.py` mit 13 Fällen. Geprüft wird der Zeilentrenner an dem Block, der in der Aufnahme zu sehen war, dazu mehrere Balken in einem Block, Blockgrenzen mitten in einer Zeile, reine Textzeilen – und am Programm selbst, dass dort nicht wieder zuerst nach `\n` gesucht wird.

Die Balkenerkennung wird gegen **echte** Zeilen der Engine geprüft, einschließlich der Gegenprobe: `Wasted space: 37.22 KB (0.02% of file data blocks)` und `Actual gain achieved: 40.97%` sind **keine** Fortschrittszeilen, obwohl sie ein Prozentzeichen tragen.

**46 Testdateien grün.**

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.44.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.44.sha256` | Prüfsummen aller Quelldateien |
| `test_protokollfeld.py` | neuer Test |
