# PS5 Dump & Image Converter v1.8.41 – Release Notes

## Zweck dieses Releases

Für die Seitenleiste lagen zwanzig Hintergrundbilder bei, für den Hauptbereich nur zehn. Zehn Motive der Seitenleiste hatten damit kein Gegenstück im Querformat – die beiden Bereiche ließen sich nicht auf dasselbe Motiv einstellen. Diese zehn Bilder sind jetzt da.

---

## Zehn neue Bilder für den Hauptbereich

Alle im Format des Hauptbereichs, 1920 × 1020 Pixel, RGB, zusammen 12,71 MiB.

| Neu | Motiv | Gegenstück in der Seitenleiste |
| --- | --- | --- |
| `bg_01_mesh-glow.png` | Gitternetz hinter einem blauvioletten Lichtschein | `sidebar_01_mesh-glow.png` |
| `bg_02_aurora.png` | Polarlichtvorhänge in Grün, Türkis und Blau | `sidebar_02_aurora.png` |
| `bg_03_light-rays.png` | Strahlenfächer aus der oberen rechten Ecke | `sidebar_03_light-rays.png` |
| `bg_04_bokeh.png` | unscharfe Lichtkreise in Violett und Blau | `sidebar_04_bokeh.png` |
| `bg_05_starfield.png` | Sternenfeld mit Nebel | `sidebar_05_starfield.png` |
| `bg_06_topo-lines.png` | Höhenlinien in Türkis | `sidebar_06_topo-lines.png` |
| `bg_07_wave-rings.png` | konzentrische Wellenringe | `sidebar_07_wave-rings.png` |
| `bg_08_grid-floor.png` | Fluchtpunktraster unter einem Horizontglimmen | `sidebar_08_grid-floor.png` |
| `bg_09_dot-matrix.png` | Punktraster mit weichem Abfall | `sidebar_09_dot-matrix.png` |
| `bg_10_diagonal-bands.png` | warme Bernsteinbänder | `sidebar_10_diagonal-bands.png` |

Damit stehen in beiden Klapplisten je zwanzig Bilder.

### Warum sie so dunkel sind

Im Hauptbereich liegen Karten, Beschriftungen und die Statuszeile über dem Bild. Die Helligkeit ist deshalb nicht frei gewählt, sondern am vorhandenen Bestand geeicht: Die zehn bisherigen Querformate `bg_11` bis `bg_20` liegen im Mittel zwischen **7,1 und 22,9** von 255. Die neuen liegen zwischen **7,9 und 18,9** – innerhalb desselben Bandes, am ruhigeren Ende.

Jedes Bild hat außerdem eine Vignette und feines Korn, wie die vorhandenen.

### Einsortiert wird nach dem Format, nicht nach dem Namen

Das Programm entscheidet allein am Seitenverhältnis, in welche der beiden Listen ein Bild gehört. Die neuen Dateien brauchten dafür keine Änderung am Programm. Nachgeprüft über die Funktion selbst: **20 Bilder für den Hauptbereich, 20 für die Seitenleiste**, keines in der falschen Liste.

---

## Das Werkzeug liegt bei

`tools\mach_hintergrundbilder.py` erzeugt die zehn Bilder. Es ist Teil der Quellen, wird aber **nicht** in die EXE eingebettet – der Ordner `tools` gehört nicht zum Lieferumfang des Programms.

    .venv\Scripts\python.exe tools\mach_hintergrundbilder.py
    .venv\Scripts\python.exe tools\mach_hintergrundbilder.py <ordner> bg_06

Die Zufallszahlen sind je Bild fest gesetzt. Ein erneuter Lauf liefert bitgleiche Dateien – nachgewiesen über SHA-256, **10 von 10 identisch**.

### Zwei Fallstricke, die dabei aufgefallen sind

Beide sind im Werkzeug behoben und dort kommentiert, weil sie bei jeder weiteren Bilderzeugung wieder auftreten würden.

**Ein Lichtfleck hinterließ eine harte Rechteckkante.** `Image.radial_gradient` aus Pillow skaliert den Verlauf auf die **Ecke** des Quadrats – an der Kantenmitte steht erst 255/√2 ≈ 180. Schlicht invertiert bleiben dort 75 stehen, außerhalb 0; der Kasten, in den der Lichtfleck gesetzt wird, zeichnet sich damit als sichtbare Kante ab. In `bg_03` war das als Sprung von 1,87 bei x = 816 messbar, genau am linken Kastenrand. Nach der Streckung um √2 ist die Maske am Kreisrand wirklich 0; derselbe Messwert liegt jetzt bei **0,35**.

**Höhenlinien lassen sich in 8 Bit nicht sauber rechnen.** Der Linienabstand ist Periode geteilt durch Steigung, die Zahl der Linien 255 geteilt durch Periode. Viele verschachtelte Linien verlangen eine kleine Periode, glatte Kanten eine große Steigung – beides zugleich sprengt den Wertebereich. In flachen Zonen folgt die Linie dann den Quantisierungsstufen statt dem Verlauf, sichtbar als Treppenstufen. Das Feld für `bg_06` wird deshalb auf 360 × 204 in Fließkomma gerechnet und erst danach hochgezogen.

---

## Nebenbei behoben: die binäre Versionsressource

In `file_version_info.txt` gibt es die Version doppelt – einmal als Zahlenfeld (`filevers`, `prodvers`) und einmal als Text. Die Zahlenfelder standen noch auf **1.8.38**, während die Textfelder mit jedem Release mitgezogen wurden. Windows zeigt beide an unterschiedlichen Stellen der Dateieigenschaften. Beide stehen jetzt auf `1.8.41.0`.

---

## Tests

Die Prüfungen rund um die Hintergrundbilder kommen ohne feste Dateinamen und ohne feste Anzahlen aus – der Bilderbestand ändert sich. Geprüft wird stattdessen, dass jedes Bild in genau einer Liste landet und die Zuordnung zum Format passt. Der Zuwachs um zehn Dateien brauchte deshalb keine Anpassung.

**476 unittest-Fälle grün**, dazu die beiden eigenen Sammlungen `test_all_quality_new` mit 14/14 und `test_build_ready` mit 8/8 – zusammen 498.

Zusätzlich zur Testsuite gemessen:

- größter Helligkeitssprung je Bild, spalten- und zeilenweise – die verbliebenen Sprünge liegen auf Motivkanten (bei `bg_08` am Fluchtpunkt x = 960 und am Horizont y ≈ 551), nicht auf Kastenrändern
- Kanalmittel jedes Bildes gegen das Band der vorhandenen zehn
- Wiederholbarkeit des Werkzeugs über SHA-256

Am fertigen Archiv nachgewiesen: **40 Hintergrundbilder** eingebettet (20 quer, 20 hoch), dazu unverändert 24 Payloads, 24 AMPR-/PlayGo-Dateien und 23 Backport-Fakelibs. Der Ordner `tools` ist nicht im Archiv.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.41.exe` | Ausführbares Programm, 99,34 MiB, x64, Versionsressource `1.8.41.0` |
| `SOURCE_FILE_MANIFEST_v1.8.41.sha256` | Prüfsummen aller Quelldateien, 309 Einträge (v1.8.40: 296) |
| `Hintergrundbilder\bg_01…bg_10` | die zehn neuen Querformate |
| `tools\mach_hintergrundbilder.py` | Werkzeug, das sie erzeugt |
| `BENUTZERHANDBUCH.html` / `.pdf` | Handbuch, Abschnitt 14.1 um den Motivgleichlauf ergänzt |
