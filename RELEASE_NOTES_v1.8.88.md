# PS5 Dump & Image Converter v1.8.88

**23.08.2026**

Kein neuer Funktionsumfang. Diese Ausgabe behebt zwei Fehler, die auffielen,
weil der Programmcode einmal gezielt danach durchsucht wurde — beide hatten
gemeinsam, dass sie **nichts meldeten**.

## Abbrechen stoppt jetzt wirklich alles

Während des Packens beobachtet ein Hintergrundvorgang die entstehende
Zieldatei und leitet daraus den Fortschritt ab. Beim Abbrechen sollte er
stehen bleiben; im Programm ist das sogar ausdrücklich als Schritt 3 des
Abbruchs beschrieben.

Der Schritt griff ins Leere. Er suchte nach einem Merkmal, das unter diesem
Namen nie angelegt wurde — kein Absturz, keine Meldung, er tat einfach nichts.

Die Folge: Nach dem Abbruch lief die Messung alle 150 Millisekunden weiter,
bis das Packen von sich aus zu Ende kam. Bei einem großen Abbild konnte das
Minuten dauern. Betroffen waren der Abbruch und beide Wege, das Programm zu
beenden.

## Ein Lesefehler führte zum Absturz statt zu einer Meldung

Beim Ermitteln von Spielname und Title-ID liest das Programm zwei Dateien aus
dem Dump. Lässt sich eine davon nicht öffnen, obwohl sie da ist — gesperrt,
fehlende Leserechte, ein Fehler auf dem Datenträger —, war eine saubere
Behandlung vorgesehen: eine Zeile ins Protokoll, und weiter geht es ohne den
Namen.

Diese Behandlung stürzte selbst ab, weil ihr eine Voraussetzung fehlte. Statt
der Protokollzeile gab es einen Programmfehler. Nachgestellt und behoben:

```
vorher:   NameError: name 'logger' is not defined
jetzt:    leeres Ergebnis, eine Zeile im Protokoll
```

## Warum das niemandem auffiel

Beide Fehler stürzen im Normalbetrieb nicht ab und melden nichts. Der eine
läuft nur bei einem Lesefehler an, den anderen sieht man höchstens daran, dass
der Rechner nach einem Abbruch noch etwas zu tun hat.

Gefunden wurden sie durch zwei Suchen, die nicht auf Symptome schauen, sondern
auf Muster im Programmcode. Für das zweite Muster gibt es jetzt eine dauerhafte
Prüfung: Sie durchsucht das Hauptprogramm nach Abfragen auf Merkmale, die
nirgends angelegt werden. Dieselbe Falle hatte das Projekt schon einmal
getroffen.

## Kleinigkeit am Rande

In den Programmtexten stand ein Eintrag doppelt (mit identischem Inhalt). Er
ist entfernt; an den 1582 Texten ändert sich nichts.

## Geprüft

**1300 Tests** laufen durch — drei mehr als in v1.8.87. Für beide Korrekturen
wurde gegengeprüft, dass die Prüfungen ohne sie fehlschlagen.

Die eingebaute Darstellungsdiagnose meldet keine Auffälligkeit: 90 vermessene
Bedienelemente, Fenster, Beschriftungen, Bilder und Skalierung passen
zusammen.

Ebenfalls durchsucht und ohne Befund: nackte Fehlerabfangblöcke (keine),
veränderbare Standardwerte in Funktionsköpfen (keine), sowie sämtliche
Stellen, an denen das Programm Transparenz oder Fensterform an Windows
übergibt — die wurden gegen das Betriebssystem nachgemessen und stimmen, auch
bei 125 % Anzeigeskalierung.
