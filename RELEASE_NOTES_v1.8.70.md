# Release Notes – v1.8.70

**Datum:** 21.08.2026
**Vorgänger:** v1.8.69

Diese Ausgabe räumt auf, was die Darstellungsprüfung aus v1.8.69 an schmalen Fenstern gemeldet hat. Alles darin wurde gemessen, nicht geschätzt – und nach der Änderung noch einmal nachgemessen.

---

## Die Werkzeugleiste faltet sich, statt sich zu quetschen

Die dreizehn Knöpfe oben brauchen zusammen rund **1515 Pixel**. Ist weniger da, lässt `pack` sie nicht weg – es drückt sie zusammen. Am 20.08.2026 gemessen:

| Fensterbreite | „BENUTZERHANDBUCH" |
| --- | --- |
| 1920 | 189 px (vollständig) |
| 1440 | 100 px |
| 1366 | **26 px** |
| 1230 | fällt ganz heraus |

Ein 26 Pixel breiter Knopf ist weder zu lesen noch zu treffen, und nichts wies darauf hin.

Reicht der Platz nicht, wandern jetzt einzelne Knöpfe ins Sammelmenü **WEITERE TOOLS ▾** – der Reihe nach KLOG, JS LOADER, FILEZILLA, BIBLIOTHEK, SHADOWMOUNT+, BENUTZERHANDBUCH, CREDITS und zuletzt DIAGNOSE. Dort stehen sie unter einem Trennstrich. Wird das Fenster wieder breiter, kommen sie an ihren Platz zurück, in der ursprünglichen Reihenfolge.

BEENDEN, DESIGN, EINSTELLUNGEN, WEITERE TOOLS und der Sprachumschalter bleiben immer stehen.

Das Sammelmenü ist ohnehin der Ort dafür: MicroMount, der AMPR-Index-Builder und zwei weitere Werkzeuge liegen aus genau demselben Grund schon dort.

---

## Die Statuszeile wird nicht mehr abgeschnitten

Die Zeile unten rechts nennt, was die gewählte Aufgabe tut („Wandelt einen Dump-Ordner in .ffpfsc (komprimiert), .ffpfs (unkomprimiert) … um"). Sie wollte **860 Pixel**; bei einem 1230 Pixel breiten Fenster standen 627 zur Verfügung. Der Rest fehlte einfach.

Sie bricht jetzt um. Dahinter steckte mehr als ein `wraplength`:

- **Die Umbruchbreite richtet sich nach der Pfad-Karte**, nicht nach der Inhaltsfläche. Dazwischen liegen rund 80 Pixel Polsterung – genau so viel fehlte beim ersten Versuch.
- **Die Beschriftungen tragen einen eingebrannten Bildausschnitt**, damit sie ohne farbigen Kasten auf dem Hintergrundbild stehen. Bei `compound="center"` bestimmt dieses Bild den Platzbedarf, nicht der Text. Der Ausschnitt wird nur bei Textwechsel neu vermessen – eine neue Umbruchbreite ändert den Text aber nicht. Ohne diese Erkenntnis war der Text umgebrochen und die Beschriftung trotzdem 860 Pixel breit.
- **Die Reihenfolge zählt:** erst umbrechen, dann einbrennen. Andersherum bekommt der Ausschnitt die Breite des ungebrochenen Textes.

---

## Kein Hintergrundbild wird mehr hochgerechnet

`bg_19_ray-burst.png` war als einziges der zwanzig Querformatbilder nur 1424 × 752 Pixel groß und wurde auf einem 1920er Bildschirm um 35 % hochgerechnet. Alle zwanzig Seitenleistenbilder waren 320 × 1000, während die Leiste bei 125 % Anzeigeskalierung 493 Pixel breit ist – 54 % Hochrechnung, und das sieht man.

Der Bildgenerator `tools/mach_hintergrundbilder.py` rechnet jetzt in beiden Formaten:

- **Ein neues `bg_19_ray-burst`** in 1920 × 1020, im selben Stil wie die übrigen.
- **Die Seitenleistenbilder 01 bis 10 und 19** entstehen als eigene Hochformat-Rechnung in **640 × 1440**.
- **Die Seitenleistenbilder 11 bis 18 und 20** sind senkrechte Ausschnitte aus dem jeweiligen Querformatbild in **640 × 1020**. Für diese Motive gibt es keinen Generator; ein Ausschnitt ist verlustfrei, während Hochskalieren nur die Weichheit festschreiben würde.

**Die neunzehn übrigen Querformatbilder bleiben unverändert** – Byte für Byte. Der Generator erzeugt bg_01 bis bg_10 exakt so wie bisher; die Umstellung auf freie Bildgrößen hat am Aussehen nichts geändert.

---

## Die Mindestbreite steigt auf 1230 Pixel

Zuletzt blieb eine Überschrift: „KOMPRESSION (PFS) / WORKER-THREADS / PRÜFUNG" braucht 387 Pixel, bekam bei 1200 aber nur 366. Statt den Text zu kürzen, richtet sich die Mindestbreite nach dem, was die Karte tatsächlich braucht.

---

## Nachgemessen

Bei 900 Pixel Fensterhöhe und Breiten von 1230, 1280, 1366, 1440, 1600 und 1920 meldet die Darstellungsprüfung **keine einzige Auffälligkeit** – kein Überstand, keine zu enge Beschriftung, kein hochgerechnetes Bild. `--anzeige-diagnose` gibt 0 zurück. Beim Verbreitern kommen die eingefalteten Knöpfe vollständig und in der richtigen Reihenfolge zurück.

- **1036 Tests grün** (3 übersprungen), 14/14 Quality-Tests.
- `test_anzeige_diagnose.py` auf 56 Fälle – unter anderem, dass das Abbestellen vor der Abkürzung steht, dass eingefaltete Knöpfe im Sammelmenü landen und dass der Umbruch vor dem Einbrennen läuft.

---

## Offen

### Kurze Fenster

Unterhalb von rund 880 Pixeln Fensterhöhe steht die Knopfleiste unten aus dem Fenster heraus. Auf einem 1366×768-Bildschirm passt der Inhalt nicht vollständig – das war vor v1.8.69 schon so (Grenze damals rund 790 Pixel) und wurde durch die höhere Pfad-Karte um 66 Pixel schlechter.

Zwei Versuche, das über die Mindesthöhe der Protokollfläche aufzufangen, brachten nichts Messbares: Ihr Platzbedarf sank von 510 auf 110 Pixel, die Zeile blieb trotzdem bei 145, und der Überstand war unverändert. Beide Versuche wurden deshalb wieder entfernt. Die Lösung wäre eine rollbare Inhaltsfläche – eine eigene Änderung.

Sonst nichts – die Darstellungsprüfung meldet bei 900 Pixeln Höhe und jeder Breite ab 1230 **keine Auffälligkeit** mehr.
