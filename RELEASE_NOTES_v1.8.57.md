# PS5 Dump & Image Converter v1.8.57 – Release Notes

## Zweck dieses Releases

Eine kleine Änderung an der Oberfläche — und eine Entscheidung **gegen** eine geplante Änderung, die eine Messung nicht überstanden hat.

---

## Der Hinweis vor der Formatwahl

Aus der ShadowMountPlus-Anleitung (1.7alpha7), also von der Seite, die das Abbild auf der Konsole einhängt:

> MkPFS uses zLib compression. Decompression is hardware-assisted, but throughput is limited to roughly `150-250 MB/s`. This is about one third of the speed of an external USB drive […] Games that read large amounts of data or stream textures continuously may stutter.

**Das stand nirgends im Programm.** Wer ein streaming-lastiges Spiel nach `.ffpfsc` packte, erfuhr es erst, wenn es auf der Konsole ruckelte — und suchte den Fehler dann vermutlich beim Packen.

Unter der Zielformat-Liste erscheint jetzt bei `.ffpfsc` und `.ffpfs` eine zweite Zeile mit genau dieser Angabe. Bei `.exfat`, `.ffpkg` und Ordner-Zielen bleibt es bei der bisherigen Anzeige der Quellarten.

### Eine Kleinigkeit, die den Unterschied macht

Der Hinweistext hing bisher allein an der **Aufgabe** und wurde nur in `_refresh_target_format_options` gesetzt. Wer die Aufgabe nicht wechselt, sondern bloß das Zielformat in der Liste umstellt — also genau der Fall, um den es hier geht —, hätte den Text nie zu sehen bekommen. Er hängt jetzt zusätzlich am `<<ComboboxSelected>>` der Formatliste.

---

## Die Blockgröße bleibt bei 65536 — gemessen, nicht vermutet

Die mkpfs-Anleitung empfiehlt bei vielen kleinen Dateien `--block-size 16384` oder `32768`, weil Blockverschnitt das Abbild aufblähen kann. Das klang plausibel und wurde geprüft.

### Schritt 1: alle 32 echten Dumps durchgerechnet

Nur **drei von 32** liegen bei 64 KB über 2 % Verschnitt: Arkanoid 5,5 %, Teardown 5,0 %, Dirt 5 3,3 %. Der Rest zwischen 0,0 % und 1,9 %.

Dabei zeigte sich, dass die naheliegende Faustregel nicht trägt: *Gear Club Unlimited 2* hat mit 6.592 Byte den **kleinsten** Median aller Dumps, verliert aber nur 1,9 % — die vielen kleinen Dateien gehen in 22 GB unter. Eine Heuristik über den Median hätte hier danebengelegen.

### Schritt 2: dreimal wirklich gepackt

Arkanoid (1,05 GB), zweistufig wie Aufgabe 1, äußere Stufe fest bei 65536:

| innerer Block | `pfs_image.dat` | fertige `.ffpfsc` |
| --- | --- | --- |
| 65536 | 1.196.425.216 | 396.754.944 |
| 32768 | 1.157.070.848 (−3,3 %) | 396.623.872 (−0,03 %) |
| 16384 | 1.140.277.248 (−4,7 %) | 396.427.264 (−0,08 %) |

**Der Verschnitt sind Nullbytes, und zlib packt sie restlos weg.** Aus 4,7 % im Zwischenabbild werden 0,1 % im Ergebnis — 327 KB von 396 MB.

Die Laufzeiten wurden miterhoben, aber **nicht ausgewertet**: Dieselbe Quelle wurde dreimal hintereinander gelesen, der Dateisystem-Zwischenspeicher begünstigte die späteren Läufe. Als Vergleich taugt das nicht.

### Schritt 3: und es wäre riskant gewesen

ShadowMountPlus beschreibt 64 KB nicht als Vorgabe, sondern als Abbildungseinheit:

- „During packing, data is zero-padded to a **64 KB** sector boundary"
- `lvd_pfs_sector_size` — „the optimized profile uses a **65536-byte LVD mapping unit**"
- für exFAT zweimal ausdrücklich: „keep the cluster size at 64 KB; **smaller clusters can reduce performance**"; `mkexfat.sh` verdrahtet `CLUSTER_SIZE=65536` fest

**mkpfs optimiert die Datei, ShadowMount+ beschreibt, was die Konsole damit tut.** Wer nur die erste Hälfte liest, spart Platz, der nach der Kompression gar nicht da war, und riskiert Lesegeschwindigkeit bei einem Format, dessen Entpackung ohnehin der Engpass ist.

Der Befund ist festgehalten, damit die Empfehlung nicht in ein paar Wochen erneut plausibel aussieht und die Messung noch einmal gemacht werden muss.

---

## Tests

**811 Prüfungen, 0 Fehlschläge.** Neu: fünf zum Hinweis — dass er bei PFS-Zielen erscheint, bei anderen nicht, die Quellenzeile nicht verdrängt und an der Formatliste hängt.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.57.exe` | Windows |
| `dist\PS5_Dump_Image_Converter_v1.8.57_linux_x86_64` | Linux x86-64 |
| `SOURCE_FILE_MANIFEST_v1.8.57.sha256` | Prüfsummen aller Quelldateien |
