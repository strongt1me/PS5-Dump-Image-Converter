# PS5 Dump & Image Converter v1.8.90

**23.08.2026**

Eine kleine, aber spürbare Änderung am Programmstart.

## Die Quelle startet leer, das Ziel bleibt stehen

Bisher standen beim Start **beide** Pfade noch so da wie beim letzten Mal.
Beim Ziel ist das bequem — bei der Quelle riskant: Ein Klick auf **START**
wandelte dann den Dump der letzten Sitzung um, und das fällt erst auf, wenn
das Ergebnis fertig ist.

| Feld | Beim Start |
| --- | --- |
| **QUELLE** | leer — muss bewusst gewählt werden |
| **ZIEL** | der zuletzt benutzte Ordner |

Der Unterschied hat einen Grund: Ein falsches **Ziel** fällt sofort auf — es
entsteht eine Datei am falschen Ort, verwechselt wird nichts. Eine falsche
**Quelle** merkt man erst am fertigen Abbild, und dann ist die Arbeit schon
getan.

Bequem bleibt es trotzdem: Der Knopf **Durchsuchen** öffnet weiterhin im
zuletzt benutzten Quellordner — das merkt sich das Programm getrennt vom
Eingabefeld. Es ist also ein Klick mehr, kein Suchen von vorn.

## Geprüft

Gemessen wurde an einer frisch aufgebauten Oberfläche, nicht am Quelltext:

```
vorher:   QUELLE = <der alte Ordner>    ZIEL = <der alte Ordner>
jetzt:    QUELLE = (leer)               ZIEL = <der alte Ordner>
```

**1304 Tests** laufen durch — vier mehr als in v1.8.89. Die neuen halten das
Verhalten fest; gegengeprüft wurde, dass sie ohne die Änderung fehlschlagen.

Ein Hinweis zur Sorgfalt bei dieser Prüfung: Ein erster Anlauf benutzte
*erfundene* Ordnerpfade — und bestand deshalb auch ohne die Änderung. Der
Grund: Einen Quellpfad, den es gar nicht gibt, verwirft das Programm ohnehin,
sobald es die gewählte Aufgabe prüft. Erst mit **wirklich vorhandenen**
Ordnern misst die Prüfung, was sie messen soll.
