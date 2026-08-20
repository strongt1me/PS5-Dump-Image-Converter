# Release Notes – v1.8.71

**Datum:** 21.08.2026
**Vorgänger:** v1.8.70

Zwei Dinge: Bei kurzen Fenstern fällt nichts mehr aus dem Bild, und der Diagnosebericht sagt jetzt auch, womit gearbeitet wird – auf Wunsch samt Abgleich mit den Quellen.

---

## Die Inhaltsspalte lässt sich rollen

Überschrift, Untertitel, Pfad-Karte, Knopfleiste, Protokollfläche und Statuszeile wollen zusammen **1356 Pixel** Höhe. Die Protokollfläche gibt nach und fängt das normalerweise auf – alles andere ist starr und braucht **844 Pixel**. War das Fenster kürzer, schob das Raster den Rest schlicht unter den Fensterrand:

| Fensterhöhe | was außerhalb stand |
| --- | --- |
| 880 | nichts |
| 840 | Statuszeile, 4 px |
| 800 | Statuszeile, 64 px |
| 768 | **Knopfleiste, 26 px** – STARTEN und ABBRECHEN |

Nicht verkleinert, sondern außerhalb: unsichtbar und nicht anklickbar, ohne jeden Hinweis. Auf einem 1366×768-Bildschirm traf das jeden, der das Programm maximiert.

Die Spalte liegt jetzt in einer Rollfläche. Reicht der Platz, ändert sich **gar nichts**: Der eingebettete Rahmen bekommt genau die Höhe des Sichtfelds, die Bildlaufleiste bleibt ausgeblendet, die Protokollfläche dehnt sich wie bisher. Erst wenn es nicht mehr reicht, behält er seine natürliche Höhe, die Leiste erscheint und alles bleibt erreichbar – auch über das Mausrad.

Drei Feinheiten stecken darin:

- **Gerechnet wird mit der Mindesthöhe, nicht mit der Wunschhöhe.** In der Wunschhöhe steckt der Wunsch der Protokollfläche nach 512 Pixeln, und die ist ausdrücklich dehnbar. Danach zu gehen hätte die Spalte immer rollen lassen, auch auf einem großen Bildschirm.
- **Das Mausrad lässt die Protokollfläche in Ruhe.** Sie rollt ihren eigenen Text; ein Rad über ihr darf nicht zusätzlich die ganze Spalte bewegen. Dasselbe gilt für Klapplisten und Zahlenfelder.
- **Die Darstellungsprüfung weiß jetzt, was rollbar ist.** Ein Überstand über den Fensterrand ist dort kein Mangel – der Teil ist erreichbar, man muss nur rollen. Ohne diese Unterscheidung hätte sie nach dem Umbau jede Zeile unterhalb des Sichtfelds gemeldet.

---

## Der Bericht nennt, womit gearbeitet wird

Neuer Abschnitt **„Mitgelieferte Werkzeuge"** – offline, in jedem Bericht, in Sekundenbruchteilen:

```
MkPFS (Packmaschine): 0.0.9  [PSBrew/MkPFS]
MkPFS (im PS4-Werkzeug): 1.0.0  [PSBrew/MkPFS]
PS4 FFPFSC: 0.2.8  [GPL-3.0-Auszug, siehe PS4FFPFSC-0.2.8/UPSTREAM.md]
Pillow: 12.3.0  [pillow]
…
FileZilla: 3.70.6.0  [https://filezilla-project.org/download.php]
AMPR-EMU-Bibliotheken: 20 (0.2.6 debug, 0.2.6 no debug …)
Backport-Fakelibs: 4 (4, 5 …)
Nutzlasten (helloworld): 25 (CheatRunner_v0.17.elf, OffAct_v0.34.elf …)
```

Die Fassungen der eingebetteten Werkzeuge werden **gelesen, nicht importiert** – ein Import zöge deren ganze Abhängigkeitskette nach sich, und ein Diagnosebericht soll nichts starten. Bei den Fremdwerkzeugen wird unter Windows die Fassung aus den Dateieigenschaften gelesen.

---

## Aktualisierungsprüfung auf Knopfdruck

Im Diagnosefenster steht ein Knopf **„Aktualisierungen prüfen"**. Er fragt die Quellen ab und hängt das Ergebnis unten an Bericht und Datei an:

```
Aktualisierungen: 2 Aktualisierungen verfuegbar, 3 ohne abfragbare Quelle

MkPFS (Packmaschine): 0.0.9 (aktuell)  PSBrew/MkPFS
MkPFS (im PS4-Werkzeug): 1.0.0 (neuer als die Quelle: 0.0.9)  PSBrew/MkPFS
cryptography: 49.0.0 -> 50.0.0 verfuegbar  cryptography
FileZilla: 3.70.6.0 (keine abfragbare Quelle)  https://filezilla-project.org/download.php
```

**Nur auf Knopfdruck**, nie beim Erstellen des Berichts: Ein Fehlerbericht darf nicht an einer Internetverbindung hängen. Die Abfrage läuft im Hintergrund, das Fenster bleibt bedienbar. Jede Adresse wird bis zu dreimal versucht – die Verbindung bricht erfahrungsgemäß häufig beim ersten Anlauf ab.

**Was ehrlich nicht geht:** FileZilla, OSFMount und die Szene-Bestände (AMPR EMU, Fakelibs, Nutzlasten) veröffentlichen keine abfragbare Fassungsliste. Dort steht, was vorliegt, und die Bezugsquelle – eine erfundene Aussage wäre schlechter als keine. Abfragbar sind GitHub-Projekte und die Python-Bibliotheken über PyPI.

Ein Praxislauf über zwölf Bestandteile brauchte 5,7 Sekunden.

---

## Prüfung

- **1071 Tests grün** (3 übersprungen), 14/14 Quality-Tests.
- Neu: `test_rollflaeche.py` (9 Fälle) – prüft über die Fensterhöhen 700, 768, 800, 840, 880, 991 und 1080, dass jede Zeile im Rollbereich liegt, dass die Leiste nur bei Bedarf erscheint und dass die Knopfleiste bei 768 Pixeln erreichbar ist.
- Neu: `test_aktualisierungen.py` (26 Fälle) – Fassungsvergleich, Beurteilung, Wiederholung bei Verbindungsabbruch, und am Quelltext, dass die Netzabfrage nicht im Bericht mitläuft.

---

## Offen

Nichts aus der Darstellungsprüfung: Sie meldet bei jeder Fensterbreite ab 1230 und jeder Höhe ab 700 **keine Auffälligkeit**.
