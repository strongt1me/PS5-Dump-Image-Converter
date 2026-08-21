# Release Notes – v1.8.77

**Datum:** 21.08.2026
**Vorgänger:** v1.8.76

Ein Nutzerhinweis, den ich für falsch hielt, war richtig — und ein Kasten, der dauerhaft im Fenster stand, gehört dorthin, wo er gelesen wird.

---

## Ein dritter Ort, der funktioniert

Der Nutzer sagte, `/mnt/usb0/etaHEN/games` gehöre in die Liste. Ich hatte Zweifel: Im Protokoll der Konsole standen beim Einstecken des Sticks nur zwei gezielte Scans, für `/mnt/usb0/homebrew` und `/mnt/usb0` — für `etaHEN/games` keiner.

Statt es zu behaupten oder zu bestreiten, wurde es gemessen: Datei versuchsweise dorthin verschoben, gewartet, danach zurückgelegt.

```text
[22:58:59] [IMG][LVD] unmount complete:
    source=/mnt/usb0/etaHEN/games/CUSA03877 - Styx_ … .ffpfsc
```

Ein Aushängen setzt ein Einhängen voraus — **es funktioniert.** Die gezielten Scans beim Einstecken nennen offenbar nur einen Teil der 34 eingebauten Pfade.

Damit sind drei Orte belegt, jeder einzeln gemessen:

| Ort | Ergebnis |
| --- | --- |
| `/mnt/usb0/` | binnen 15 Sekunden gefunden |
| `/mnt/usb0/homebrew/` | binnen 20 Sekunden eingehängt |
| `/mnt/usb0/etaHEN/games` | binnen 20 Sekunden eingehängt |
| `/mnt/usb0/ps4ffpsc/` | nie gefunden |
| `/data/homebrew`, `/data/etaHEN/games` | Kernel Panic |

Ein Test hält die drei fest, mit der Messung im Kommentar — damit beim nächsten Mal niemand wieder zweifelt.

## Das PS4-Fenster ist wieder aufgeräumt

Der Ablageort-Kasten und die Hinweiszeile darunter standen **dauerhaft** im Fenster, obwohl man sie einmal liest und danach nie wieder braucht. Beides ist jetzt ausschließlich in der Einblendung während der Umwandlung — dort erreicht der Hinweis den Nutzer im richtigen Moment, nämlich während er ohnehin auf den Balken wartet.

| | Fensterhöhe nötig | verfügbar |
| --- | --- | --- |
| v1.8.74 | 1012 px | 1000 px — **überlief** |
| v1.8.76 | 959 px | 1000 px |
| v1.8.77 | **769 px** | 1000 px |

Damit ist die Enge, gegen die in den letzten drei Ausgaben angekämpft wurde, endgültig vorbei: 231 Pixel Reserve statt zuletzt 41 und davor einem einzigen.

## Die Einblendung bleibt 25 Sekunden

Sie trägt jetzt den ganzen Text: Überschrift, die drei Zeilen, die gemessenen Belege und die Einschränkung des eingebetteten Werkzeugs. Vier Absätze lesen sich nicht in fünfzehn Sekunden.

Alles andere unverändert — viermal über den Vorgang verteilt (bei 8 / 32 / 56 / 80 %), langsam ein- und ausgeblendet, kein Klick nötig, keine Einblendung nach dem Ende.

## Nachgeprüft

1172 Tests grün, drei übersprungen. Angepasst wurden vier Tests, die den alten Zustand beschrieben: Sie prüfen jetzt, dass die Texte in der **Einblendung** stehen. Dazu zwei neue — einer stellt sicher, dass Kasten und Hinweiszeile **nicht** ins Fenster zurückwandern, einer hält die drei gemessenen Orte fest.

Ein Test verlangte wörtlich „nie gefunden"; gemeint war die Aussage, dass ein eigener Ordner nichts bringt. Er prüft jetzt die Aussage statt das Wort und akzeptiert auch „nicht gefunden".

**Eine Beobachtung ohne Handlungsbedarf:** In einem von drei Gesamtläufen fiel `test_ffpkg_progress_sync.py::test_subprocess_callback_receives_cr_record_before_process_exit` aus, allein und in zwei weiteren Gesamtläufen grün. Ein zeitkritischer Test um Fortschrittsmeldungen aus einem Unterprozess — nicht Teil dieser Änderung, aber vermerkt, damit er nicht in Vergessenheit gerät.
