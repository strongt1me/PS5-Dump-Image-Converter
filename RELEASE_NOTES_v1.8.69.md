# Release Notes – v1.8.69

**Datum:** 20.08.2026
**Vorgänger:** v1.8.68

Diese Ausgabe dreht sich um die Darstellung des Programmfensters: zwei Fehler an den Hintergrundbildern, richtige Maßangaben in den Einstellungen – und eine Prüfung, die solche Fehler künftig selbst findet.

---

## Zwei Fehler an den Hintergrundbildern

Beide betrafen dieselbe Mechanik: Jede der vier Flächen (Fenster, Inhaltsfläche, Seitenleiste, Aktionsleiste) rechnet ihr Hintergrundbild neu, sobald Tk ihr eine Größenänderung meldet. Fällt diese Meldung aus oder kommt sie zur falschen Zeit, holt es nichts nach – der nächste Anstoß käme erst, wenn jemand das Fenster anfasst.

### Beim Start wurde das Fensterbild nie gerechnet

`_on_root_configure` steigt aus, solange die Startphase läuft. Danach kommt keine Meldung mehr, wenn niemand am Fenster zieht. Das Fensterhintergrundbild blieb deshalb in der Größe der Bilddatei stehen.

Am 20.08.2026 gemessen:

```
Hintergrundbild (gezeichnet): 1424x752
Fläche:                       1920x991
zuletzt angepasst auf:        nie
```

Inhaltsfläche und Seitenleiste hatten zur selben Zeit die richtigen Maße. `_finish_startup_phase` zieht jetzt einmal alle vier Flächen nach, mit Wiederholung, solange das Fenster noch keine Größe hat.

### Ein Designwechsel hinterließ die Zwischengröße

Beim Umschalten des Designs baut sich die Oberfläche neu auf. Dabei meldet die Inhaltsfläche kurz **1600** statt 1427 Pixel Breite und die Seitenleiste **320** statt 493 – die angemeldeten Maße, bevor Tk sie auf die tatsächliche Anzeigeskalierung bringt. Für diese Zwischengröße wird eine Anpassung bestellt (80 ms verzögert).

Die unmittelbar folgende, endgültige Meldung nahm dann die Abkürzung „passt doch schon" – und ließ den veralteten Auftrag stehen. Der lief 80 ms später trotzdem und überschrieb das richtige Bild mit der Zwischengröße. Dort blieb es.

Zwei Änderungen:

- **Abbestellen steht jetzt vor der Abkürzung.** Ein offener Auftrag wurde für eine frühere Größe bestellt und ist damit immer veraltet.
- **Verglichen wird gegen das gezeichnete Bild, nicht gegen einen gemerkten Wert.** `_last_*_resize_size` konnte von der Wirklichkeit abweichen; ein `PhotoImage` kann das nicht.

Zusätzlich prüft `_on_layout_settled` nach jeder Größenänderung, ob alle vier Flächen ihr Bild in der richtigen Größe tragen, und zieht nach, wo nicht.

---

## Die Maßangaben in den Einstellungen

Bei der Bildauswahl standen feste Zahlen: 1920 × 1020 für den Hauptbereich, 320 × 1000 für die Seitenleiste. Die zweite war schlicht falsch – die Seitenleiste ist mit `width=320` angemeldet, wächst bei 125 % Anzeigeskalierung aber auf **493 Pixel**. Jedes mitgelieferte Seitenleistenbild wird dort um 54 % hochgerechnet.

Der Hinweis rechnet die nötige Größe jetzt aus Bildschirmauflösung und tatsächlicher Leistenbreite aus, statt sie zu behaupten.

Ein zu kleines Bild wird weiterhin angenommen – es wirkt dann weich gezogen. Verzerrt wird nie: Das Bild wird formatfüllend gerechnet und der Überstand mittig beschnitten.

---

## Die Darstellungsprüfung

Der Diagnosebericht trägt jetzt ganz oben eine Urteilszeile und darunter zwei neue Abschnitte.

**Geprüft wird:**

| Was | Woran es auffällt |
| --- | --- |
| Zusammengedrückte Elemente | sichtbar, aber ohne Ausdehnung, obwohl Platz gebraucht wird |
| Abgeschnittene Elemente | stehen über den Fensterrand hinaus |
| Zu enge Beschriftungen | Knopf schmaler als sein eigener Text |
| Hochgerechnete Bilder | Datei kleiner als die Fläche, mit Prozentangabe |
| Stehengebliebene Bilder | gezeichnete Größe passt nicht zur Fläche |
| Anzeigeskalierung | DPI-Bewusstsein, `tk scaling` gegen Fenster-DPI, Schrifthöhe |
| Laufruhe | Arbeitsspeicher samt Zuwachs, angesammelte Bilder und Zeitgeber, Reaktionszeit |

Bildlabels ohne Text werden bei den Beschriftungen ausgenommen – die Hintergrundlabels liegen absichtlich über ihren Rand hinaus.

Abrufbar über den Diagnose-Knopf oder ohne Oberfläche:

```
PS5_Dump_Image_Converter_v1.8.69.exe --anzeige-diagnose
PS5_Dump_Image_Converter_v1.8.69.exe --anzeige-diagnose --voll
```

Rückgabe 0 bei sauberer Darstellung, 1 bei Befunden, 2 wenn die Prüfung selbst scheiterte.

Unter Windows braucht das ein Terminal mit Administratorrechten: Die EXE fordert diese über ihr Manifest an, also bevor überhaupt Programmcode läuft – aus einer gewöhnlichen Eingabeaufforderung startet sie gar nicht erst. Unter Linux und macOS sowie beim Start aus dem Quelltext entfällt das.

---

## Laufruhe: gemessen, nicht behauptet

Acht Runden aus je acht Aufgabenwechseln, vier Größenänderungen und Designwechseln:

| | Start | nach Runde 8 |
| --- | --- | --- |
| Arbeitsspeicher | 125 MB | 123 MB |
| Bilder im Speicher | 22 | 21 |
| offene Zeitgeber | 2 | 1 |
| Reaktionszeit | 0,0 ms | 0,0 ms |

Kein Zuwachs, keine Ansammlung.

---

## Prüfung

- **1030 Tests grün** (3 übersprungen), 14/14 Quality-Tests.
- Neu: `test_anzeige_diagnose.py` mit 45 Fällen – die Prüfregeln einzeln, dazu Quelltextprüfungen für die Reihenfolge in den vier Größenwachen. Der Fehler lag zwischen zwei Ereignissen, die 80 ms auseinanderliegen; am laufenden Fenster ist er nicht zuverlässig zu treffen, an der Reihenfolge im Quelltext dagegen eindeutig.

---

## Offen

Zwei Bildbestände bleiben zu klein für einen 1920er Bildschirm bei 125 % Anzeigeskalierung. Die Prüfung meldet beides:

- `bg_19_ray-burst.png` ist 1424 × 752 – die anderen neunzehn Querformatbilder sind 1920 × 1020.
- Alle zwanzig Seitenleistenbilder sind 320 × 1000, gebraucht werden rund 500 Pixel Breite.

Hochskalieren brächte nichts; für beide gibt es keine Quelle in höherer Auflösung.

### Die Zeile mit Kompression, Prüfstufe und Integration ist zu lang

Die Prüfung fand das am fertigen Linux-Programm auf einem 1366 Pixel breiten Bildschirm. Die Zeile ist eine feste Kette ohne Umbruch und braucht **1145 Pixel** Kartenbreite – vorhanden sind bei einem 1920er Bildschirm 1347, darunter weniger:

| Fensterbreite | Karte | ragt hinaus |
| --- | --- | --- |
| 1920 | 1347 | – |
| 1600 | 1027 | 118 px (Firmware-Liste) |
| 1440 | 867 | 278 px (ab AMPR-Version) |
| 1366 | 793 | 352 px |
| 1100 (Mindestbreite) | 527 | 618 px, schon ab der Prüfstufe |

Der überstehende Teil ist nicht sichtbar und nicht bedienbar. Betroffen ist, wer das Fenster kleiner als rund 1725 Pixel zieht; maximiert auf einem 1920er Schirm passt alles.

Ein Umbruch braucht eine zusätzliche Rasterzeile in der Pfad-Karte – direkt unter der Zeile beginnt bei y=184 der Hinweistext zum Quellformat, senkrechter Spielraum ist also keiner da. Das ist eine eigene Änderung mit eigenem Test und steht als Nächstes an. Die Teilursache reicht bis v1.8.56 zurück: Schon die Prüfstufen-Liste allein überschreitet bei der Mindestbreite den Kartenrand.
