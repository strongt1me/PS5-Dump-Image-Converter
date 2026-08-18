# PS5 Dump & Image Converter v1.8.37 – Release Notes

## Zweck dieses Releases

Gemeldet wurde, dass im neuen **BACKPORT**-Fenster nicht alle Knöpfe sichtbar sind. Die Untersuchung ergab zwei unabhängige Fehler und – bei der anschließenden Prüfung **aller** Fenster – dieselbe Ursache an drei weiteren Stellen.

---

## Fehler 1: Die Knopfleiste wurde zusammengedrückt

Ein Bereich mit `pack(fill="both", expand=True)` beansprucht den gesamten freien Raum. Wird er **vor** einer festen Knopfleiste gepackt und reicht die Fensterhöhe nicht, bleibt der Leiste nur der Rest.

Gemessen im Backport-Fenster:

```
Button 'Backport starten'  210x28  statt  210x54
Button 'Nur prüfen'        150x28  statt  150x51
Button 'Schließen'         150x28  statt  150x51
```

Bei 28 statt 51 Pixeln fällt die zentrierte Beschriftung weg – übrig bleibt ein leeres Rechteck. Die Reihenfolge ist jetzt umgedreht: erst die feste Leiste an den unteren Rand, dann die dehnbare Liste in den verbleibenden Raum.

### Betroffen waren

| Fenster | Befund | Behebung |
| --- | --- | --- |
| **PKG-MERGER** | **0 sichtbare Knöpfe** – die Leiste war ganz aus dem Fenster gedrängt | Packreihenfolge |
| **BACKPORT** | 3 Knöpfe auf 28 px | Packreihenfolge |
| **DOWNLOADS** | 5 Knöpfe auf 24 px | Packreihenfolge |
| **ShadowMount+ / MicroMount** | 4 Knöpfe auf 41 px, „Auf PS5 schreiben…" 226 statt 242 px breit | Packreihenfolge, Fenster 840 statt 800 px breit, Tabelle 12 statt 16 Zeilen |
| **JS Loader** | „Konsole leeren" **8 px** breit | Aktionsknöpfe auf zwei Zeilen verteilt |

Beim JS Loader brauchten die fünf Knöpfe nebeneinander 1233 px bei 1113 px Fensterbreite. Die vier linksbündigen füllten die Zeile, der rechtsbündige bekam den Rest.

---

## Fehler 2: Die Firmware-Auswahl blieb leer

Die Auswahlliste im Backport-Fenster zeigte nichts an. Ursache war eine `StringVar`, die nur als lokale Variable existierte und auf die keine Closure zugriff: Mit dem Ende der Aufbaufunktion wurde sie eingesammelt, und das Widget zeigte auf eine nicht mehr vorhandene Variable.

**Dass trotzdem „Firmware 7.00" in der Statuszeile stand, war Zufall.** Ohne Auswahl liefert `current()` den Wert `-1`, und `FIRMWARE_MIT_FAKELIBS[-1]` ist in Python der *letzte* Eintrag – hier zufällig ebenfalls 7.00. Bei einer anderen Listenreihenfolge hätte das Programm stillschweigend die falsche Firmware genommen.

Behoben an beiden Enden: Die Auswahlliste kommt ohne Variable aus, und die Auswertung fällt bei `-1` ausdrücklich auf die Voreinstellung zurück statt auf den letzten Eintrag.

---

## Geprüft wurden alle 19 Fenster

| Fenster | Knöpfe | Befund |
| --- | --- | --- |
| BACKPORT | 3 | behoben |
| DOWNLOADS | 9 | behoben |
| ShadowMount+ | 8 | behoben |
| MicroMount | 10 | behoben |
| JS Loader | 6 | behoben |
| Dump umbenennen, Einstellungen, Design, Credits, Ressourcen, Diagnose, Debug-PKG, AMPR-Index, KLOG, Bibliothek, Spiel-Info | – | ohne Beanstandung |
| PARAM/MANIFEST (neu und geöffnet) | 5 | ohne Beanstandung |
| PKG-Merger | 2 | **behoben** |
| FTP-Client (eingebauter) | 12 | ohne Beanstandung |

Diese drei brauchten eine echte Vorbedingung, um sich überhaupt zu öffnen: PARAM/MANIFEST beantwortete Rückfragen, der PKG-Merger bekam einen Ordner mit geteilten `.pkg`-Dateien, und beim FTP-Client musste der Start des externen FileZilla unterbunden werden – sonst baut das Programm sein eigenes Fenster gar nicht erst.

**Drei Fehlalarme wurden verworfen:** Das Schließzeichen `✕` in den eigenen Titelleisten von *Ressourcen* und *Spiel-Info* meldet 34 statt 44 Pixel Höhe. Diese Leisten sind mit `pack_propagate(False)` bewusst auf 34 px festgelegt; das Zeichen ist rund 15 px hoch und vollständig sichtbar. Die Prüfung übergeht solche Leisten jetzt.

Ebenso gemeldet wurde eine „leere Combobox“ im Param-Editor. Nachgemessen: Steht `applicationDrmType` in der Datei, zeigt das Feld `standard`; fehlt der Schlüssel, bleibt es leer. Ein Editorfeld muss „nicht gesetzt“ darstellen können – die Prüfung bemängelt Comboboxen dort nicht mehr.

Und zwei Fenster schienen zunächst den Tk-Baum abzureißen. Ursache war jeweils ein echter Dialog, den die Messung nicht abgefangen hatte und der bis zum Zeitlimit blockierte – ein Fehler im Prüfskript, nicht im Programm.

---

## Absicherung

Neu ist `test_fensterlayout.py`. Es öffnet die betroffenen Fenster am laufenden Tk-Baum und misst jeden sichtbaren Knopf gegen seine angeforderte Größe – am Quelltext allein ist dieser Fehler nicht zu erkennen. Dazu vier Quelltextprüfungen, die die Packreihenfolge und den Rückfall der Firmware-Auswahl festhalten.

| Prüfung | Umfang | Ergebnis |
| --- | --- | --- |
| Neue Tests `test_fensterlayout.py` | 11 | grün |
| Gesamte Testsuite | 424 | grün (2 übersprungen) |
| Messung aller Fenster | 19 (drei davon mit hergestellter Vorbedingung) | keine Beanstandung |

---

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `PS5ImageConverter_Pro_FINAL_revised.py` | Packreihenfolge in fünf Fenstern, Firmware-Auswahl, zweite Knopfzeile im JS Loader |
| `ps5_validator/utils/i18n.py` | „Als Update/Patch umsortieren" → „Umsortieren" plus erklärender Hinweis |
| `test_fensterlayout.py` | **neu** – 11 Tests |
