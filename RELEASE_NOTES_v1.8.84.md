# PS5 Dump & Image Converter v1.8.84

**22.08.2026**

Werkzeugfenster bleiben vor dem Hauptfenster.

## Das Ärgernis

Ein Fenster aus der oberen Leiste offen, dann den nächsten Knopf gedrückt —
und das erste war weg. Es lag hinter dem Hauptfenster. Bei drei offenen
Fenstern waren nach kurzer Zeit zwei davon verschwunden.

## Die Ursache

Nicht das Öffnen des zweiten Fensters. Sondern der **Klick auf das
Hauptfenster**, den man braucht, um überhaupt an den nächsten Knopf zu kommen:
Der holt das Hauptfenster nach vorn. Die Werkzeugfenster hatten bisher keinen
Besitzer — sie waren eigenständige Fenster, und Windows hatte keinen Anlass,
sie oben zu halten.

An der echten Z-Reihenfolge nachgemessen:

```text
vorher                              nachher
HAUPTFENSTER   Platz 4              HAUPTFENSTER   Platz 9
SHADOWMOUNT+   Platz 6  dahinter    SHADOWMOUNT+   Platz 8
DIAGNOSE       Platz 5  dahinter    DIAGNOSE       Platz 7
KLOG           Platz 3              KLOG           Platz 6
                                    CREDITS        Platz 5
                                    BIBLIOTHEK     Platz 4
                                    AMPR-INDEX     Platz 3
```

Der erste Versuch, den Fehler nachzustellen, schlug übrigens fehl: `SetForegroundWindow`
ordnet innerhalb des eigenen Prozesses nicht um. Erst mit `lift()` war er
reproduzierbar — und damit auch beweisbar behoben.

## Die Lösung

Die Fenster bekommen das Hauptfenster als **Besitzer**. Damit hält Windows sie
garantiert davor.

Das kostet normalerweise den **Taskleisten-Eintrag** und den Platz im
Alt-Tab-Wechsler — und der war hier ausdrücklich gewollt. Beides holt der
Stil `WS_EX_APPWINDOW` zurück, ohne die Zuordnung aufzugeben. Nachgemessen:
Der Stil allein genügt. Das sonst übliche Aus- und Einblenden, damit er
greift, entfällt — es hätte bei **jedem** Öffnen sichtbar geflackert.

Alle sieben geprüften Fenster stehen weiterhin in der Taskleiste.

## Drei Fenster gingen an der gemeinsamen Routine vorbei

21 Fenster entstehen über `_build_modern_toplevel`, drei nicht — darunter
**CREDITS**, einer der Knöpfe aus der Werkzeugleiste. Die wären sonst weiter
zurückgefallen. Die Zuordnung steckt jetzt in einem gemeinsamen Helfer, den
alle vier Stellen aufrufen.

Nicht angefasst wurden die rahmenlosen Einblendungen (Info-Popup, „Was man
sonst ev. noch braucht"), der Kurzhinweis und der Startbildschirm — die haben
kein eigenes Fensterverhalten. Ein Test hält fest, dass das so bleibt.

## Was Sie merken werden

Weil die Fenster jetzt zum Hauptfenster gehören, **wandern sie mit ihm in die
Taskleiste, wenn Sie es minimieren** — und kommen beim Wiederherstellen
zurück. Für Werkzeugfenster ist das das übliche Verhalten, aber es ist eine
Änderung gegenüber vorher.

## Tests

Sechs neue in `test_fensterlayout.py`: dass der gemeinsame Erbauer bindet,
dass der Helfer zuordnet, dass der Taskleisten-Eintrag zurückgeholt wird, dass
das ohne Flackern geschieht, dass auch die drei Fenster daneben gebunden sind
— und dass die rahmenlosen Einblendungen ausgenommen bleiben.
**1195 Tests laufen durch**, die Darstellungsprüfung meldet keine
Auffälligkeit.

## Handbuch

Kapitel 13 hat einen Kasten dazu bekommen: dass sich mehrere Werkzeugfenster
nebeneinander offen halten lassen, vorn bleiben, ihren Taskleisten-Eintrag
behalten — und mit dem Hauptfenster minimieren.
