# PS5 Dump & Image Converter v1.8.45 – Release Notes

## Zweck dieses Releases

v1.8.44 reparierte das Protokollfeld – aber nur an einer von **zwei** Stellen. Eine zweite Bildschirmaufnahme zeigte, dass bei manchen Aufgaben weiterhin Text und Fortschrittsbalken aneinanderklebten. Dazu kommt das Ergebnis eines vollständigen Praxistests.

---

## Die zweite Stelle

Es gibt zwei Wege, auf denen Engine-Ausgaben ins Protokollfeld kommen:

| Weg | Engine | in v1.8.44 |
| --- | --- | --- |
| Zeilenweise über einen Leser | MkPFS (läuft im Prozess) | repariert |
| Am Stück über `communicate()` | UFS2Tool, makefs (eigener Prozess) | **offen** |

Auf dem zweiten Weg kommt die gesamte Ausgabe als ein Block an. `_clean_log_text` entfernt darin jedes `\r` **ersatzlos** – aus

```
==============================\r[###########-]  97% extract @ 96.35 MB/s
```

wurde

```
==============================[###########-]  97% extract @ 96.35 MB/s
```

Genau das war in der Aufnahme zu sehen, und zwar bei den Aufgaben, die `.exfat` oder `.ffpkg` erzeugen. Bei den MkPFS-Aufgaben war das Feld nach v1.8.44 bereits ruhig – dieselbe Aufnahme belegt auch das.

**Behoben:** Kommt Text am Stück herein, gilt jedes einzelne `\r` als Zeilenwechsel, und das Ganze läuft über denselben Weg, der Fortschrittszeilen zusammenfasst. Mit genau dem Muster aus der Aufnahme geprüft: aus fünf Aktualisierungen werden **drei Zeilen**, null verklebt.

Die Weiche sitzt bewusst **nach** der Kommandozeilenausgabe und dem Fehlerpuffer für Diagnosen – ein früherer Entwurf sprang davor ab und hätte beides übersprungen. Drei Tests halten die Reihenfolge fest.

---

## Praxistest: alle acht Aufgaben, zwei Sicherungen

Gefahren gegen die fertige EXE, nicht gegen den Quelltext.

| Sicherung | Größe | Dateien |
| --- | --- | --- |
| Personality and Psychology Premium (PPSA07029) | 724 MB | 68 |
| Arkanoid – Eternal Battle (PPSA06328) | 1073 MB | **1166** |

**31 Läufe, alle mit Exit-Code 0.** Aufgabe 1 in alle vier Zielformate, Aufgaben 2, 3 und 4 in je alle zulässigen Zielformate, dazu 5 und 6, und Aufgabe 8 auf Ordner und alle drei Container.

### Der Rundlauf ist bitgleich

Verglichen wird dateiweise über SHA-256, nicht über die Gesamtgröße:

| Sicherung | geprüfte Wege | Ergebnis |
| --- | --- | --- |
| Personality | Aufgabe 2, 3, 4, 5, 6 | **5 × bitgleich** (68 Dateien) |
| Arkanoid | Aufgabe 2, 3, 4 | **3 × bitgleich** (1166 Dateien) |

Arkanoid ist dabei der interessante Fall: 1166 Einzeldateien, und nach dem Weg durch `.ffpfsc`, `.exfat` und `.ffpkg` kommen alle mit identischer Prüfsumme zurück.

### Aufgabe 7 und die Konsole

Alle vier Aktionen exit 0 (anwenden, Index, wiederherstellen, entfernen). Anschließend auf `/data/homebrew` hochgeladen und von der Konsole zurückgelesen:

| Paket | Größe | Prüfung |
| --- | --- | --- |
| `Personality and Psychology Premium (PPSA07029) ohne AMPR.ffpfsc` | 103 MB | Größe und SHA-256 gleich |
| `Personality and Psychology Premium (PPSA07029) mit AMPR EMU/` | 70 Dateien, 724 MB | Stichproben bitgleich |

`eboot.bin` trägt auf der Konsole `-rwxrwxrwx` – das Ausführungsrecht, an dem v1.8.38 gescheitert war.

### Werkzeuge

17 Fenster geöffnet, alle bauen sich fehlerfrei auf, kein Bedienelement außerhalb des sichtbaren Bereichs. Inhaltlich geprüft: **SELF-Inspektor** (erkennt `eboot.bin` als signierte Hülle, Magic `SELF (0x1D3D154F)`), **DIAGNOSE** (Bericht mit Version, System, Quelle) und **PARAM/MANIFEST** (liest Content-ID, Title-ID und Version der echten `param.json`).

Nicht prüfbar war der **PKG-Merger**: Er braucht geteilte `.pkg`-Dateien, die es auf dem Testsystem nicht gibt.

---

## Tests

**46 Testdateien grün.** `test_protokollfeld.py` deckt jetzt 16 Fälle ab, darunter beide Wege ins Protokollfeld und die Reihenfolge, in der die Weiche greifen muss.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.45.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.45.sha256` | Prüfsummen aller Quelldateien |
