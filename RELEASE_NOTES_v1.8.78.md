# Release Notes – v1.8.78

**Datum:** 22.08.2026
**Vorgänger:** v1.8.77

Eine Auskunft, die zu spät kam, und zwei Fehler, die erst eine echte Konvertierung ans Licht gebracht hat.

---

## Das PS4-Fenster sagt, für welche Konsole ein Titel ist

Anlass war eine Zeile aus der Nachprüfung: „Es ist ein PS4-Titel. Die PS5-Marker gehören dort nicht hinein und fehlen zu Recht." Richtig — nur stand sie erst da, **nachdem** das Abbild fertig gebaut war. Wer eine PS5-PKG in dieses Fenster legt, wartet also den ganzen Vorgang ab, um zu erfahren, dass er im falschen Fenster ist.

Jetzt steht es beim Einlesen in einer eigenen Spalte:

| Title-ID | Konsole | Titel | Version | Bestandteile |
| --- | --- | --- | --- | --- |
| CUSA00775 | PS4 | Tetris® Ultimate | 01.00 | 0 Patch(es), 0 DLC |

Erkannt wird an der Title-ID — dieselbe Zuordnung, die das Programm beim Patch-Abruf ohnehin schon nutzt:

| Kennung | Konsole |
| --- | --- |
| `CUSA`, `PUSA` | PS4 |
| `PPSA`, `PPSS`, `PPUS`, `PPJP` | PS5 |
| alles andere, etwa `NPUB` (PS3) | **unklar** |

Meldet der Entpacker die Plattform selbst mit, zählt sie als Rückfall; die Kennung wiegt schwerer. Was sich nicht zuordnen lässt, wird **nicht geraten** — dann steht dort „unklar" und im Protokoll die Bitte, selbst nachzusehen.

Ein PS5-Titel bleibt nicht bei einer Spalte weiter rechts: Die Zeile wird in der Warnfarbe hervorgehoben, und im Protokoll steht der Verweis auf die Aufgaben 1 bis 6. Dieses Fenster baut Abbilder aus PS4-Paketen.

Gemessen am laufenden Fenster mit einer echten PKG: Überschriften `Title-ID | Konsole | Titel | Version | Bestandteile`, Zeile `('CUSA00775', 'PS4', 'Tetris® Ultimate', '01.00', '0 Patch(es), 0 DLC')`. Die Fenstergröße bleibt bei 980 × 769 Pixeln.

## Die Nachprüfung hat nie stattgefunden

Nach jedem Bau meldete das Protokoll, das fertige Abbild werde geprüft — und unmittelbar danach:

```text
Das Abbild ließ sich nicht nachprüfen: [Errno 13] Permission denied: 'E:\Test\ps4ziel2'
```

Der Pfad verrät es: Das ist der **Zielordner**, nicht die erzeugte Datei. Der Prüfung wurde von Anfang an das Falsche übergeben. Sie ist damit seit ihrer Einführung kein einziges Mal gelaufen, obwohl im Protokoll stand, dass sie läuft — und obwohl genau sie sagen soll, was wirklich im Abbild steht.

Aufgefallen ist das nicht im Test, sondern bei einer echten Konvertierung an einem echten Spiel. Jetzt sucht das Programm die gebaute Datei im Zielordner und bevorzugt dabei die zur Title-ID und zum gewählten Format — im selben Ordner können ältere Abbilder liegen. Findet es nichts, kommt eine verständliche Meldung statt eines Fehlers.

Ergebnis am Testtitel: **113 Dateien**, keine Beanstandung.

## Die Einblendung geht nicht mehr nach dem Ende auf

Zu v1.8.77 stand in den Release Notes „keine Einblendung nach dem Ende". Das stimmte nicht ganz: Der letzte Sprung des Fortschrittsbalkens auf 100 % kommt, nachdem der Vorgang bereits aufgeräumt hat — und konnte den Hinweis nachträglich auslösen. Auch das kam bei der echten Konvertierung heraus, nicht im Test.

Der Vorgang merkt sich jetzt, dass er fertig ist. Nach dem Ende erscheint nichts mehr.

Alles andere unverändert: viermal über den Vorgang verteilt (bei 8 / 32 / 56 / 80 %), 25 Sekunden, langsam ein- und ausgeblendet, kein Klick nötig.

## Nachgeprüft

**1158 Tests grün**, drei übersprungen. Zwölf davon sind neu:

* sieben zur Konsolenerkennung — die Kennungen, das Nicht-Raten bei `NPUB` und Leerem, die Rangfolge zwischen Kennung und mitgelieferter Angabe, die Spalte in der Liste, die Hervorhebung, die Texte in beiden Sprachen;
* fünf zu den beiden Fehlern — dass der Ordner nicht wieder als Abbild durchgereicht wird, dass die richtige Datei unter mehreren gefunden wird, dass ohne Abbild eine Meldung statt eines Fehlers kommt, und dass nach dem Ende keine Einblendung mehr aufgeht.

Die Konsolenspalte wurde zusätzlich am laufenden Fenster mit einer echten PKG nachgemessen, nicht nur im Test nachgebildet.

**Zur Zahl:** In den Notes zu v1.8.77 standen 1172 Tests. Der Gesamtlauf über alle 59 Testdateien liefert reproduzierbar 1158; die höhere Zahl war ein Zählfehler. An den Tests selbst wurde nichts entfernt.

## Bekannt, aber nicht angerührt

`test_ffpkg_progress_sync.py::test_subprocess_callback_receives_cr_record_before_process_exit` fiel vor zwei Ausgaben in einem von drei Gesamtläufen aus und war seither in jedem Lauf grün. Ein zeitkritischer Test um Fortschrittsmeldungen aus einem Unterprozess — weiterhin vermerkt, damit er nicht in Vergessenheit gerät.
