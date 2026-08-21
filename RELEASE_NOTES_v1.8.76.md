# Release Notes – v1.8.76

**Datum:** 21.08.2026
**Vorgänger:** v1.8.75

Ein Hinweis nützt nur, wenn man ihn liest. Diese Ausgabe stellt ihn dorthin, wo man ohnehin hinschaut — und korrigiert, was daran falsch war.

---

## Der Hinweis kommt jetzt von selbst

Während eine PS4-Konvertierung läuft, wartet man auf den Balken. Genau dann blendet sich ein, worauf es beim fertigen Abbild ankommt:

**Es darf nur vom externen USB-Datenträger starten, nie von der internen SSD.** Von dort gestartet reißt es die Konsole mit sich — an der Konsole dreimal gemessen.

| Vorgabe | Umsetzung |
| --- | --- |
| viermal im ganzen Vorgang | Marken bei 8 / 32 / 56 / 80 % |
| 15 Sekunden sichtbar | `_PS4_HINWEIS_DAUER = 15000` |
| langsam ein- und ausblenden | 600 ms in 30-ms-Schritten, Deckkraft 0 → 1 → 0 |
| nichts drücken müssen | kein Knopf, kein `grab_set`, kein `focus_force` |

Verteilt wird nach **Fortschritt statt Uhrzeit**: Ein kleines Spiel ist in zwei Minuten fertig, ein großes braucht eine Stunde — an den Prozenten liegt die Verteilung in beiden Fällen richtig. Springt der Balken, verfallen die übersprungenen Marken, damit nicht vier Einblendungen hintereinander kommen. Bei 0 % kommt keine; da schaut man noch auf den Knopf.

Gemessen an einem simulierten Lauf von 0 auf 100 %: genau vier Auslösungen, Deckkraft von 0,05 auf 1,00 über 48 steigende Schritte, jede verschwindet ohne Zutun, am Ende steht keine offen.

## Richtigstellung: `/mnt/usb0/homebrew/` funktioniert doch

In v1.8.74 stand im PS4-Fenster **„Unterordner werden nicht durchsucht"**. Das war zu pauschal — und hätte jemanden von einem Ordner abhalten können, der funktioniert.

Nachgemessen, indem die Datei versuchsweise dorthin verschoben und danach zurückgelegt wurde:

| Ort | Ergebnis |
| --- | --- |
| `/mnt/usb0/` | gefunden, binnen 15 Sekunden indiziert |
| `/mnt/usb0/homebrew/` | **gefunden, binnen 20 Sekunden eingehängt** |
| `/mnt/usb0/ps4ffpsc/` | nie gefunden, obwohl stundenlang dort |
| `/data/homebrew` (intern) | Kernel Panic |

Der Beleg aus dem Protokoll der Konsole:

```text
[20:46:56] [IMG][LVD] unmount complete:
    source=/mnt/usb0/homebrew/CUSA03877 - Styx_ … .ffpfsc
```

Ein Aushängen setzt ein Einhängen voraus. ShadowMount+ durchsucht also nicht „keine Unterordner", sondern **nur die Pfade seiner eingebauten Liste**. `<usb>/homebrew` steht darauf, ein selbst angelegter Ordner nicht.

## Drei Zeilen statt sieben

Der Kasten im PS4-Fenster sagt jetzt das Nötige und sonst nichts:

```text
NUR VOM USB-DATENTRÄGER STARTEN
✓  Auf den USB-Datenträger: /mnt/usb0/ oder /mnt/usb0/homebrew/
✗  Nie auf die interne SSD – /data/homebrew und /data/etaHEN/games geben einen Kernel Panic
!  Eigene Ordner wie /mnt/usb0/ps4ffpsc/ werden nie gefunden
```

Die Überschrift nennt die Regel selbst statt nur das Thema. Die Einzelheiten — gemessene Zeiten, was nach einem Absturz zu tun ist — stehen im Tooltip und in der Einblendung, wo sie niemandem Platz wegnehmen.

**Nebeneffekt:** Jede Zeile passt jetzt in eine statt in zwei. Der Kasten schrumpft von 177 auf 128 Pixel, das Fenster braucht **959 statt 1012** von 1000 verfügbaren. Vorher war es einen Pixel vom Überlaufen entfernt.

## Zwei Fehler, die die eigenen Tests gefangen haben

**Ein Toplevel ohne Farbe im Erzeuger.** `test_sidebar_vorschau` prüft, dass jedes neue Fenster seine Hintergrundfarbe schon im Konstruktor bekommt — Tk zeichnet es sonst zuerst weiß. Bei einer *Einblendung* wäre das besonders sichtbar aufgeblitzt.

**Ein zu knappes Zeitbudget im eigenen Test.** Die Blende bekam drei Sekunden. Laufen zwei Oberflächen auf einer gemeinsamen Tk-Wurzel, feuern die `after`-Schritte verzögert und sie braucht mehrere Sekunden statt 600 ms. Kein Produktfehler — im Betrieb läuft nur eine Oberfläche —, aber der Test log dadurch. Budget auf acht Sekunden.

## Nachgeprüft

1170 Tests grün, darunter 15 neue in `test_ps4_einblendung.py`: dass es genau vier sind, dass während einer laufenden keine zweite startet, dass ein Sprung im Balken nicht vier hintereinander auslöst, dass ein zweiter Lauf sie wieder zeigt, dass sie ohne Tastendruck verschwindet und dass ein Abbruch keine offene stehen lässt.
