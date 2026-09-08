Der Abschluss der großen Durchsicht: die letzten drei Punkte der
Befundliste. Sie steht damit auf **127 erledigt, 5 ohne Handlungsbedarf,
0 offen**.

## Der Backport sagt jetzt, ob es einen Weg zurück gibt

Die Rückfrage vor dem Start lautete bisher nur:

> Alle ausführbaren Dateien in … werden auf Firmware 7.00 herabgesetzt und
> neu signiert. **Die Originale werden dabei ersetzt.** Fortfahren?

Ob dabei eine Sicherung angelegt wird, stand nirgends. Wer den Haken
abgewählt hatte, bestätigte das, ohne zu wissen, dass es keinen Rückweg gibt:
Bricht der Lauf mittendrin ab, ist der Dump **zum Teil bearbeitet** — einige
Dateien herabgesetzt, andere nicht, und beides ist von außen nicht zu
unterscheiden. Gesagt hat das Programm es erst hinterher, im Fehlerdialog.

Jetzt steht es in der Rückfrage:

> **ACHTUNG: Es wird KEINE Sicherung angelegt.** Bricht der Lauf mittendrin
> ab, ist der Dump zum Teil bearbeitet – einige Dateien herabgesetzt, andere
> nicht – und das lässt sich nicht rückgängig machen.

Beziehungsweise, wenn gesichert wird:

> Vorher wird eine vollständige Sicherung des Ordners daneben angelegt.
> Bricht der Lauf ab, lässt sich der Ausgangszustand daraus wiederherstellen.

Damit die Angabe stimmt, läuft die **Platzprüfung jetzt vor** der Rückfrage.
Sie kann ein gewünschtes „mit Sicherung" noch in ein „ohne" verwandeln — wenn
neben dem Dump keine 40 bis 100 GB frei sind. Vorher wurde erst gefragt und
danach entschieden.

## Kleineres

- Die heruntergeladene `filezilla_setup.exe` (rund 12 MB) blieb nach jedem
  Anlauf im Temp-Ordner liegen — auch bei einem Fehlschlag. Sie wird jetzt in
  jedem Fall wieder entfernt.
- Der Docstring des Credits-Fensters versprach ein rahmenloses Fenster. Das
  war es nie: ein gewöhnliches Fenster mit Titelleiste.

---

### Zur Durchsicht insgesamt

Über die Fassungen v1.9.11 und v1.9.12 hinweg wurden **70 offene Punkte**
einer Befundliste vom 04.09. abgearbeitet: 11 waren bereits erledigt, 44
wirklich noch da, 5 stellten sich als kein Handlungsbedarf heraus. Dazu kamen
**sieben Fehler, die in der Liste gar nicht standen** — gefunden von neuen
Prüfungen, die beim Beheben entstanden sind.

Die dreizehn Punkte aus dem Abgleich mit der ShadowMountPlus-Anleitung wurden
gegen **1.7alpha13fix1** neu erarbeitet. Ergebnis: alle dreizehn waren bereits
abgedeckt — Formatrangfolge, exFAT-Clustergröße (64 KiB), Suchpfade,
fakelib/BackPork und der Entpackdurchsatz stehen im Programm.

Gesamtlauf: **2602 bestanden, 0 Fehlschläge.**

### Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.12.exe` | Windows 64-bit |
| `PS5_Dump_Image_Converter_v1.9.12_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.9.12.sha256` | Prüfsummen der Quelldateien |

Beide Programmdateien laufen eigenständig; es muss nichts nachinstalliert
werden.
