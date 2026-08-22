# Release Notes – v1.8.80

**Datum:** 22.08.2026
**Vorgänger:** v1.8.79

v1.8.79 hat erklärt, warum die Trophäen scheitern. Diese Ausgabe behebt es.

---

## Der Knopf NP-BINDUNG

Unten links im PS4-Fenster, neben EINLESEN. Er holt die `sce_sys/npbind.dat` aus dem fertigen Abbild und legt sie über FTP nach `/system_data/priv/appmeta/<Title-ID>/npbind.dat`.

Das ist genau der Handgriff, der bei der Fehlersuche zum Ziel führte: ShadowMount+ kopiert beim Registrieren nur `sce_sys/trophy2/npbind.dat` und `sce_sys/uds/npbind.dat` — beides PS5-Pfade. Ein PS4-Spiel legt seine NP-Bindung flach ab, sie ist im Abbild enthalten und wird nie abgeholt. Ohne sie meldet die Konsole bei jedem Start `Trophy registration failed (0x80551618)`.

An der laufenden Konsole geprüft:

```text
[CUSA00775] Lege die NP-Bindung auf die PS5 (532 Bytes, 192.168.1.94) …
[CUSA00775] Die NP-Bindung liegt bereits auf der Konsole – nichts zu tun.
```

### Eine Bestätigung, die zählt

Die `npbind.dat` aus unserem Abbild ist **byteweise identisch** mit der, die der Package Installer für denselben Titel ablegt — gleiche Größe, gleiche Prüfsumme. Der Schritt legt also nicht irgendetwas hin, sondern exakt die Datei, die dorthin gehört.

### Wann er zu drücken ist

Erst, wenn das Spiel auf der PS5 bereits erscheint. Der Zielordner entsteht mit der Registrierung — beim Bauen liegt das Abbild noch auf dem PC. Deshalb ist es ein eigener Knopf und kein Schritt im Bauvorgang. Ist der Titel noch nicht registriert, sagt das Protokoll genau das, statt eine Fehlermeldung zu werfen.

### Was er nicht tut

**Er überschreibt nie.** Liegt schon eine Bindung da, bleibt sie unangetastet — auch wenn sie vom Abbild abweicht. Bei einem regulär installierten Titel hat die des Systems Vorrang; der Schritt füllt nur die Lücke, die ShadowMount+ lässt. Nach dem Ablegen wird die Datei zurückgelesen und verglichen; eine halbe Datei wäre schlimmer als gar keine.

## Was vorher geprüft und verworfen wurde

Der naheliegendere Weg wäre gewesen, die Datei beim Bauen zusätzlich nach `sce_sys/trophy2/` und `sce_sys/uds/` ins Abbild zu legen — dann hätte ShadowMount+ sie von selbst abgeholt, ohne FTP und ohne Knopf.

Das wurde gebaut und **an der Konsole widerlegt**. ShadowMount+ kopiert sie dann nach `appmeta/<Title-ID>/trophy2/`, und dort liest das System bei einem PS4-Titel nicht nach:

| Wo die Datei lag | echter Start | Trophäenfehler |
| --- | --- | --- |
| flach in `appmeta/<Title-ID>/` | ja | **0** |
| nur in `trophy2/` | ja | **1** |

Beide Läufe mit vollständiger Startsequenz (`SplashScreen`, `LaunchFlow`, `EXEC /app0/eboot.bin abi=ps4`). Ein erster Anlauf hatte nur ein Fortsetzen aus dem Ruhezustand erwischt — das Ergebnis sah gleich aus, hätte aber am Resume-Pfad liegen können, deshalb wurde es mit einem echten Neustart wiederholt.

## Eine Korrektur unterwegs

Der Knopf hieß zuerst „NP-BINDUNG NACHTRAGEN". Mit 287 Pixeln schob er die Knopfleiste auf 1027 Pixel und schnitt **ABBRECHEN ab**. Ausgemessen: Im 980er Fenster sind rund 232 Pixel frei. Mit der kurzen Beschriftung ist das Fenster wieder bei 980 × 769, die Leiste braucht 897. Ein Test hält die Längengrenze fest.

## Voraussetzung

Die Adresse der PS5 muss in den Einstellungen hinterlegt und die Konsole per FTP erreichbar sein — dieselbe Verbindung, die auch der AMPR EMU Manager nutzt. Fehlt die Adresse, weist das Fenster darauf hin, statt stillschweigend nichts zu tun.

## Nachgeprüft

**1179 Tests grün**, drei übersprungen. Sieben neue: Zielpfad, fehlender Ordner, fehlende Datei (wird abgelegt), vorhandene gleiche und vorhandene abweichende Datei (beide bleiben unangetastet), der Knopf im Fenster, die Beschriftungslänge und die Meldungen in beiden Sprachen.

Der Ablegen-Fall lässt sich an einer echten Konsole nicht auslösen, ohne etwas kaputtzumachen — er wird deshalb gegen eine nachgebildete Verbindung geprüft, die mitschreibt, was hochgeladen wurde. Der Nicht-Überschreiben-Fall ist an der echten PS5 gemessen.

Handbuch 13.8 um einen eigenen Abschnitt zum Knopf erweitert.
