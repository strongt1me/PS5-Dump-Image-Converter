# PS5 Dump & Image Converter v1.8.35 – Release Notes

## Zweck dieses Releases

Neue Funktion **BACKPORT**: Ein Spiel, das ein zu neues SDK verlangt, lässt sich auf eine ältere Firmware herabsetzen. Bisher war dafür ein separates Programm nötig, das eine .NET-Laufzeit voraussetzt. Die Verfahren sind hier nachgebaut – das Programm braucht nichts weiter als sich selbst.

---

## Wie es funktioniert

Jede ausführbare PS5-Datei trägt in einem Modulkopf (`sceProcessParam` bzw. `sceModuleParam`) die SDK-Version, mit der sie gebaut wurde. Die Konsole vergleicht sie beim Start mit ihrer eigenen Firmware und verweigert alles, was zu neu ist. Diese Angabe steht unverschlüsselt in der Datei.

Der Ablauf je Datei – die Reihenfolge ist zwingend:

| Schritt | Was geschieht |
| --- | --- |
| 1 | Typ bestimmen: SELF, ELF oder nicht ausführbar |
| 2 | SELF → ELF entpacken (bei SELF) |
| 3 | SDK-Angabe im Modulkopf herabsetzen |
| 4 | optionaler `libc.prx`-Zeichenkettenpatch (nur 6.xx) |
| 5 | ELF → SELF neu signieren – **nicht optional** |
| 6 | Original ersetzen, erst nach Schritt 5 |

Nie signieren, bevor gepatcht wurde; nie den libc-Patch nach dem Signieren; nie das Original anfassen, solange nicht beide Schritte gelungen sind.

**Nichts davon entschlüsselt etwas.** Die Segmentdaten eines fake-signierten SELF liegen im Klartext im Container; das Entpacken ist reines Umkopieren an die ELF-Offsets.

### Zielfirmware und Ersatzbibliotheken

| Firmware | PS5-SDK | PS4-SDK | Bibliothekssatz |
| --- | --- | --- | --- |
| 4.00 | `0x04000031` | `0x09040001` | 4 Dateien |
| 5.00 | `0x05000033` | `0x09590001` | 4 Dateien |
| 6.00 | `0x06000038` | `0x10090001` | 8 Dateien |
| 7.00 | `0x07000038` | `0x10590001` | 7 Dateien (inkl. `ps5-backpork.elf`) |

Die Sätze liegen der EXE bei (4,81 MB) und landen als Ordner `fakelib` neben dem Spiel. Ohne sie erwartet ein herabgesetztes Spiel Bibliotheken, die es auf der älteren Firmware nicht gibt.

---

## Sicherheiten

- **Sicherung vor dem ersten Zugriff.** Standardmäßig entsteht neben dem Spielordner eine vollständige Kopie mit Zeitstempel.
- **Alles im Arbeitsspeicher.** `datei_verarbeiten()` schreibt grundsätzlich nichts; erst der Aufrufer ersetzt – über eine `.neu`-Datei und `os.replace`, also in einem Zug.
- **Nur herabsetzen.** `muss_gepatcht_werden()` verlangt `aktuell > ziel`. Angehoben wird nie.
- **Kennung wird geprüft.** Ein Typtreffer im Programmkopf genügt nicht; die Kennung im Segment selbst muss stimmen, sonst würde bei einer beschädigten Datei ins Leere geschrieben.
- **`fakelib` bleibt außen vor.** Die mitgelieferten Bibliotheken passen bereits und werden nicht noch einmal herabgesetzt.

---

## Ein Fehler in der Vorlage, hier behoben

Ein SELF-Container legt je Segment **zwei** Einträge ab: einen Meta-Eintrag mit den Prüfsummen und einen Daten-Eintrag mit dem Segment selbst. Nur der Daten-Eintrag trägt Bit 11 (*hat Blöcke*); sein `segment_index` zeigt auf den zugehörigen Programmkopf. Beim Meta-Eintrag zeigt dasselbe Feld dagegen auf den **Partner-Eintrag**.

Die Referenzimplementierung unterscheidet beide nicht – der entsprechende Filter ist dort auskommentiert. Dadurch werden 32 Byte Prüfsumme an eine völlig fremde Stelle kopiert. An einem echten Backup fiel das auf:

```
Eintrag  props               idx  Ziel-p_offset
 4       0x0000000000510004    5  0x0            ← Meta-Eintrag, schreibt auf Offset 0
```

Ergebnis: Der ELF-Kopf wurde mit Nullen überschrieben, die Datei war unbrauchbar. Hier werden Meta-Einträge übergangen.

---

## Prüfung

### An echten Dateien

Fünf Backups, **57 SELF-Dateien**, 145 MB bis 50 GB Spielgröße:

| Prüfung | Ergebnis |
| --- | --- |
| Alle Dateien entpacken zu gültigem ELF | 57/57 |
| Rundlauf SELF → ELF → SELF → ELF | 57/57 |
| Tatsächlich herabgesetzt (Ziel 4.00) | 28 |
| Verarbeitungsfehler | 0 |

Der Rundlauf vergleicht Byte für Byte, was ein SELF-Container per Definition erhält: den ELF-Kopf, die vollständige Programmkopftabelle und die Dateibereiche aller signierten Segmente. Einziger zulässiger Unterschied ist `e_shnum → 0` – Abschnittsköpfe werden nicht übernommen, wie in `make_fself.py`.

Vorgefundene SDK-Stände: 1.00 (5×), 2.00 (12×), 3.00 (12×), 7.00 (14×), 9.00 (3×), 10.00 (11×).

### Vollständiger Durchlauf an einer Arbeitskopie

`Arcade Zone` (SDK 7.00) wurde auf `E:\Test` kopiert und auf Firmware 4.00 gebracht:

| Prüfung | Ergebnis |
| --- | --- |
| Dateien herabgesetzt | 14 von 15 (eine ohne SDK-Angabe) |
| Alle geänderten Dateien tragen die Zielfirmware | ja |
| Sicherung angelegt und enthält die Originale | 15/15 unverändert |
| Ersatzbibliotheken kopiert | 4/4 |
| `.neu`-Reste | keine |
| Dauer | 21,4 s |

### Tests

| Prüfung | Umfang | Ergebnis |
| --- | --- | --- |
| Neue Tests `test_backport.py` | 52 | grün |
| Gesamte Testsuite | 379 | grün (2 übersprungen) |
| Oberfläche mit echtem `mainloop` | 15 Punkte | 15/15 |

---

## Grenzen

- **Nicht echt signiert.** Das Ergebnis läuft nur auf einer bereits gejailbreakten Konsole.
- **Kein Erfolgsversprechen.** Ob ein Spiel nach dem Backport startet, hängt vom Spiel ab; manche verlangen Funktionen, die es auf der älteren Firmware nicht gibt. Der Hinweis steht auch im Fenster.
- **An echter Hardware bestätigt (16.08.2026).** Terminator 2D, SDK 10.00 → 7.00, sechs Dateien herabgesetzt und neu signiert – startet und läuft auf einer PS5 (Firmware 12.00, gestartet vom USB-Stick). In einem zweiten Durchgang **mit** den Ersatzbibliotheken blendet die Konsole „Spiel backportiert“ ein und das Spiel läuft ebenfalls – damit ist die vollständige vorgesehene Konfiguration bestätigt. Die Kette entpacken → patchen → neu signieren ist praktisch belegt. Nicht belegt ist, dass ein Backport auf einer echten 4.00-bis-7.00-Konsole einen sonst unmöglichen Start ermöglicht – das konnte hier niemand prüfen.
- **`libc`-Patch experimentell.** Standardmäßig aus.

---

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `ps5_validator/utils/ps5_backport.py` | **neu** – Typerkennung, SELF↔ELF, SDK-Patch, Signieren, Firmware-Profile |
| `Backport_Fakelibs/{4,5,6,7}/fakelib/` | **neu** – 23 Ersatzbibliotheken, 4,81 MB |
| `PS5ImageConverter_Pro_FINAL_revised.py` | Backport-Fenster, Arbeitsablauf, Menüeintrag |
| `ps5_validator/utils/i18n.py` | 50 neue Schlüssel, deutsch und englisch |
| `PS5ImageConverter_Pro.spec` | Bibliothekssätze eingebettet, zwei Module ergänzt |
| `test_backport.py` | **neu** – 52 Tests |

---

## Grundlagen

Die Verfahren stammen aus der Szene und sind hier nachgebaut:

- **BestPig** – BackPork, Verfahren und Starter `ps5-backpork.elf`
- **idlesauce** – ursprüngliches Downgrade-Skript
- **john-tornblom** – `make_fself.py`, Vorlage für den Signierteil
- **CyB1K** – SelfUtil, Vorlage für das Entpacken
- **PS5 BackPork Kitchen** – Firmware-Profile und Bibliothekssätze
