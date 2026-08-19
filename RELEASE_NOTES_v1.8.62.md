# PS5 Dump & Image Converter v1.8.62 – Release Notes

## Zweck dieses Releases

Drei Anzeigefehler, gefunden beim Nachsehen am fertigen v1.8.61 — **zwei davon in dem Fenster, das dieselbe Version neu gebracht hat.**

---

## Was gefunden wurde, und wie

Die gebaute `.exe` lässt sich hier nicht starten: Sie fordert im Manifest `requireAdministrator` an (wegen OSFMount und Dokan), ein nicht-interaktiver Start bricht an der Rechteabfrage ab. Geprüft wurde deshalb zweigleisig — das Bündel von innen und dasselbe Programm aus der Quelle, mit Bildschirmfotos.

### Die Beschriftung über der hellsten Stelle

**„PRÜFUNG NACH DEM PACKEN"** war kaum zu lesen. Der Grund war nicht die Farbe: Sie hatte dieselbe wie „QUELLE" und „ZIELFORMAT", und sie bekommt denselben gedämpften Bildausschnitt als Untergrund. Sie sitzt nur an einer anderen Stelle — rechts neben der Klappliste, und dort liegt bei den üblichen Hintergrundbildern der helle Teil des Motivs.

Sie ist jetzt hell geschrieben. Die übrigen Beschriftungen bleiben, wie sie waren; sie liegen über dunklen Bereichen und sind dort gut lesbar.

### Das neue Fenster war 671 Pixel zu breit

`ps5_autoloader` ging auf **1651 statt 980 Pixel** auf. Ursache: sieben Knöpfe nebeneinander. Das Fenster wächst seit v1.8.60 auf seinen Inhalt — hier wuchs es also korrekt, aber auf ein Maß, das auf einem kleineren Bildschirm wieder an der Bildschirmkante abgeschnitten worden wäre. **Genau der Fehler, den v1.8.60 beseitigt hat, an neuer Stelle wieder eingebaut.**

Jetzt zwei Knopfreihen: 980 × 900 Pixel.

### Und die Überschrift fehlte

Jedes Werkzeugfenster trägt innen Titel und Untertitel. `ps5_autoloader` fing mitten im Hinweistext an. Nachgezogen über denselben Weg wie überall sonst.

---

## Ein Fehlalarm, der keiner werden durfte

Auf dem ersten Bildschirmfoto sah „Schnappschuss zurückspielen" blau aus wie ein Akzentknopf — obwohl im Code nur der erste Knopf diesen Stil bekommt. Die Abfrage des Widgets ergab `(TButton)`, kein Akzentstil: **Es war der Mauszeiger, der darüber stand.**

Ohne diese Nachfrage wäre eine Zeile Code „repariert" worden, die in Ordnung ist.

---

## Was am Bündel geprüft wurde

Da die `.exe` nicht startbar ist, wurde ihr Inhalt gelesen statt angenommen: 1155 Archiveinträge, darunter `AMPR_EMU/0.3.5 no debug`, 40 Hintergrundbilder, 33 MkPFS-Dateien und der Bibliothekssatz FW7. Im eingebetteten Python-Archiv (404 Module) trägt `ps5_backport` alle sechs neuen Funktionen der Deckungsprüfung, `i18n` die neuen Texte, und das Hauptskript alle zehn neuen Methoden dieser Fassung.

---

## Tests

**893 Prüfungen, 0 Fehlschläge.**

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.62.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.62_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.62_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.62_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.62.sha256` | Prüfsummen aller Quelldateien |
