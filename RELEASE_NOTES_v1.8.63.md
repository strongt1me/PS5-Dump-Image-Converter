# PS5 Dump & Image Converter v1.8.63 – Release Notes

## Zweck dieses Releases

Gemeldet mit fünf Bildausschnitten: Die Beschriftungen auf der Karte sind schwer zu lesen. Nachgereicht: der Rahmen soll etwas mehr Deckkraft bekommen.

---

## Warum die Texte schlecht lesbar waren

Nicht wegen der Farbe an sich. `fg_secondary` – ein gedämpftes Grau – ist auf einer einfarbigen Fläche genau richtig und wird überall im Programm so benutzt. Diese Texte liegen aber auf dem **Hintergrundbild**, und wo dessen Motiv hell wird, bleibt vom Grau kaum etwas übrig.

Aufgefallen war das zuerst bei **„PRÜFUNG NACH DEM PACKEN"** (v1.8.62): Die Beschriftung sitzt rechts neben der Klappliste und damit über der hellsten Stelle der üblichen Bilder. Die übrigen lagen über dunkleren Bereichen – deshalb fiel es dort später auf, nicht weil sie anders behandelt wurden.

Jetzt tragen **alle** Texte auf der Karte dieselbe helle Farbe:

QUELLE · ZIELFORMAT · KOMPRESSION (PFS) / WORKER-THREADS / PRÜFUNG · PRÜFUNG NACH DEM PACKEN · der Formathinweis samt „Quelle: …" · ZIELORDNER · TEMP-ORDNER · „Rechner nach erfolgreichem Abschluss herunterfahren"

Dazu die **Statuszeile und die Telemetriezeile** unter der Karte: Sie liegen auf demselben Bild und hatten dasselbe Problem, waren aber nicht Teil der Meldung.

**Als eine Konstante, nicht achtmal einzeln.** `_KARTEN_TEXT_ROLLE` steht an einer Stelle im Quelltext. Acht verstreute Farbangaben laufen beim nächsten Mal auseinander – eine davon wäre übersehen worden, und niemand hätte gewusst, welche.

---

## Der Rahmen: 10 Punkte mehr Deckkraft

Die Karte trägt jetzt zu **60 %** ihre eigene Farbe statt zu 50 %; das Bild scheint entsprechend zu 40 % durch (`BG_CARD_IMAGE_OPACITY` von 0.50 auf 0.40). Das Motiv bleibt klar erkennbar – der Grundzustand, der so gewollt ist –, steht der Schrift aber nicht mehr im Weg.

---

## Ein Fehler, den niemand gemeldet hat

Beim Wechsel des Farbschemas im laufenden Betrieb zieht das Programm die Schriftfarben aus einer Tabelle nach. Zwei Einträge fehlten darin: **„PRÜFUNG NACH DEM PACKEN"** und das **Kästchen zum Herunterfahren**.

Folge: Die Aufhellung aus v1.8.62 wäre beim ersten Wechsel von Dunkel auf Hell wieder verschwunden – und der Fehler hätte so ausgesehen, als sei die Änderung nie angekommen. Beide stehen jetzt drin.

---

## Tests

**893 Prüfungen, 0 Fehlschläge.**

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.8.63.exe` | Windows |
| `PS5_Dump_Image_Converter_v1.8.63_linux_x86_64` | Linux x86-64 |
| `PS5_Dump_Image_Converter_v1.8.63_macos_arm64.dmg` | macOS, Apple Silicon |
| `PS5_Dump_Image_Converter_v1.8.63_macos_x86_64.dmg` | macOS, Intel |
| `SOURCE_FILE_MANIFEST_v1.8.63.sha256` | Prüfsummen aller Quelldateien |
