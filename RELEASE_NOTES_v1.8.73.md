# Release Notes – v1.8.73

**Datum:** 21.08.2026
**Vorgänger:** v1.8.72

Ein Bereich der Oberfläche sah unordentlich aus. Diese Ausgabe sagt, warum – und räumt auf.

---

## Der Befund

Das Bedienfeld unter ZIELFORMAT wirkte ungeordnet, ohne dass sich benennen ließ, woran das liegt. Nachgemessen am laufenden Fenster bei 125 % Skalierung waren es vier Dinge:

| Was | Gemessen |
| --- | --- |
| Senkrechter Versatz in der Einbauzeile | **6 px** über fünf Elemente (y=218 bis y=224) |
| Abstände in derselben Zeile | 5, 8, 15, 5 px |
| Breite der gemeinsamen Überschrift über drei Feldern | 387 px |
| Abstand zwischen Kästchen und Hinweistext | **1 px** |

## Warum die Elemente nicht auf einer Linie standen

Jedes Bedienelement hing mit `rely=0.5, anchor="w"` am **vorherigen**. Das ist so lange harmlos, wie alle gleich hoch sind. Sind sie es nicht – ein Kästchen ist 25 px hoch, eine Klappliste 34 –, muss Tk bei jedem Schritt auf einen halben Pixel runden. Über eine Kette von fünf Elementen summiert sich das auf sechs Pixel.

Zwei weitere Eigenheiten kamen dazu, die eine reine Rechnung unbrauchbar machen:

- `place -in` misst ab dem **inneren** Rand des Bezugselements. Ein Kästchen mit Rahmen verschiebt damit alles um ein Pixel.
- `winfo_width()` liefert direkt nach einem `place` noch den Wert von vorher.

Deshalb rechnet der neue `_kartenzeile_ausrichten` die Breiten nicht mehr aus. Er hängt **alle** Elemente einer Zeile an dasselbe Bezugselement – das erste –, wirft sie einmal grob an ihre Stelle und **misst dann nach**, wie sie tatsächlich stehen. Die Abweichung wird weggerechnet, waagerecht wie senkrecht. Zwei Durchgänge genügen; stimmt bereits alles, verschiebt der zweite nichts mehr.

## Warum es damit noch nicht getan war

Nach dem ersten Ausrichten blieb eine Lücke bei 16 statt 8 Pixeln stehen. Der Grund: Das Zahlenfeld für die Worker bekommt in `_worker_spin_hoehe_angleichen` den Stil `Perf.TSpinbox` mit engerem Innenabstand – und wird dadurch **nach** dem Ausrichten noch acht Pixel schmaler.

Ein einmaliges Ausrichten kann das nicht auffangen. Eine `<Configure>`-Wache zieht die Zeilen jetzt nach, sobald sich irgendwo eine Breite ändert. Sie schaukelt sich nicht auf: Während des Ausrichtens ist sie stumm, und ein Lauf, bei dem die Abstände schon stimmen, verschiebt nichts und löst damit auch keine neuen Ereignisse aus. Dieselbe Wache fängt einen Sprachwechsel, einen Designwechsel und eine geänderte Anzeigeskalierung mit ab.

## Eine Überschrift für drei Felder sagt nichts

Über Kompression, Worker-Anzahl und Prüfstufe stand eine einzige 387 px breite Zeile:

```text
KOMPRESSION (PFS) / WORKER-THREADS / PRÜFUNG
[6 – Ausgewogen]  [4]  [Schnell]
```

Welches Wort zu welchem Kasten gehört, war daraus nicht abzulesen. Jetzt trägt jedes Feld seine eigene Beschriftung, bündig darüber gesetzt und automatisch mitwandernd, wenn sich links davon eine Breite ändert.

## Eine Abstandssprache für die ganze Karte

| Abstand | Bedeutung | Beispiel |
| --- | --- | --- |
| 8 px | gehört zusammen | Kästchen AMPR EMU und seine Fassungsliste |
| 16 px | eigenständige Einstellung | Zielformat, Kompression, Worker, Prüfung |

Mehr als 16 px gibt die Breite nicht her, und das ist nachgerechnet: Die vier Felder der oberen Zeile sind zusammen 565 px breit, die Karte ist bei der Mindestfensterbreite 657 px breit. Drei Abstände zu je 16 px lassen 14 px Reserve; bei 20 px wären es nur noch zwei.

Der engere Abstand hatte einen sichtbaren Nebeneffekt: Die Beschriftungen **WORKER** und **PRÜFUNG** standen nur acht Pixel auseinander und lasen sich als ein Wort.

## Die Einbau-Zeile nutzt jetzt den freien Platz rechts

Rechts neben PRÜFUNG blieb die halbe Karte leer, während sich AMPR EMU, PlayGo und BACKPORT eine Zeile tiefer drängten. Ist die Karte breit genug, stehen sie jetzt oben in derselben Zeile – fünf Beschriftungen auf einer Linie, die Bedienelemente in einer Reihe darunter, und die Karte wird **66 Pixel niedriger** (528 statt 594).

Das geht nicht bedingungslos. Die Zeile braucht 513 Pixel, die obere endet bei 643 – zusammen mit dem Gruppenabstand also 1172 Pixel. Die Karte ist 573 Pixel schmaler als das Fenster, der Umschlagpunkt liegt damit bei rund **1780 Pixel Fensterbreite**:

| Fenster | Karte | Einbau-Zeile |
| --- | --- | --- |
| 1230 (Minimum) | 657 | eigene Zeile |
| 1450 | 877 | eigene Zeile |
| 1700 | 1127 | eigene Zeile |
| 1780 | 1207 | neben der Prüfstufe |
| 1920 | 1347 | neben der Prüfstufe |

Der Rückfall ist kein Beiwerk. Ohne ihn stünde das Ende der Kette bei schmalem Fenster **außerhalb der Karte** – nicht verkleinert, sondern unsichtbar und nicht anklickbar. Genau dieser Fehler wurde in v1.8.69 behoben, und die Prüfung `_einbauzeile_passt_daneben()` hält ihn fern.

Eine Feinheit war dabei nötig: Das AMPR-Kästchen ist 25 Pixel hoch, die Klapplisten der oberen Zeile 37. Auf gleicher Mitte sitzt das Kästchen deshalb tiefer – seine Überschrift, über ihm ausgerichtet, säße acht Pixel unter den anderen vieren. Sie hängt jetzt an der Prüfstufe statt am Kästchen und steht damit auf derselben Linie.

## Nachgeprüft

Ein eigener Test misst die fertige Karte am laufenden Tk-Baum aus: `test_kartenzeilen.py`, 19 Prüfungen – acht am Quelltext, elf an der Oberfläche.

| Geprüft | Ergebnis |
| --- | --- |
| Beschriftungen | alle auf y=120 |
| Bedienelemente obere Zeile | alle auf y=145 |
| Kästchen Einbauzeile | alle auf gleicher Höhe (y=222 unten, y=152 daneben) |
| Abstände obere Zeile | 16 / 16 |
| Abstände Einbauzeile | 8 / 8 / 16 / 8 |
| Platzbedarf bei Mindestbreite | 643 von 657 px |
| Umbruch hin und zurück | bei 1780 px Fensterbreite |
| Alle fünf Beschriftungen | auf einer Linie |

Dazu eine Breitenprobe von 1230 bis 1920 Pixeln in beiden Sprachen – ohne Beanstandung – und die eingebaute Darstellungsdiagnose (`--anzeige-diagnose`), die 88 Bedienelemente vermisst und nichts findet.

Insgesamt 336 Tests aus 11 Dateien laufen durch.

## Was sich nicht ändert

An dem, was das Programm mit deinen Dateien macht, ändert sich nichts. Keine neue Funktion, keine geänderte Ausgabe, keine andere Datei auf der Platte. Es geht ausschließlich um die Anordnung.
