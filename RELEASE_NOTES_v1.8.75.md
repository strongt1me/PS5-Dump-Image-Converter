# Release Notes – v1.8.75

**Datum:** 21.08.2026
**Vorgänger:** v1.8.74

**Am Programm ändert sich nichts.** Diese Ausgabe fasst ausschließlich die Testreihe an. Wer v1.8.74 benutzt, verpasst keine Funktion und keine Fehlerbehebung.

Sie ist trotzdem eigenständig, weil das mitgelieferte Prüfsummen-Verzeichnis jetzt den kompletten Testbestand mitführt — und weil drei Ursachen behoben sind, die Testläufe unzuverlässig machten.

---

## Der Testbestand liegt jetzt offen

Bisher schloss `.gitignore` den Testbestand aus. Die Regel ging nicht auf: Sieben von 58 Dateien lagen trotzdem im Repository, älter als die Regel. Wer nachvollziehen wollte, womit eine Aussage im Changelog belegt ist, fand die Prüfungen nicht.

Jetzt kommen alle 58 mit, zusammen rund 860 KB Text.

Dabei zwei Sammelfehler behoben: `test_all_quality.py` und `test_all_quality_new.py` haben eine Ausgabehilfe `test_result(name, passed, details="")`, die nur eine Zeile druckt. pytest hielt sie wegen des Präfixes für einen Test und meldete `fixture 'name' not found`. Sie umzubenennen hätte 18 Aufrufstellen getroffen — stattdessen trägt sie jetzt `__test__ = False`.

## Drei Ursachen für unzuverlässige Läufe

Ein Test schlug in einem Gesamtlauf fehl und lief in vier weiteren durch. Dahinter steckten drei voneinander unabhängige Dinge.

### 1. Eine zerstörte Tk-Wurzel

```python
def _tk_verfuegbar() -> bool:
    wurzel = tk.Tk()
    wurzel.destroy()      # beim Import
    return True
```

Dazu baute `setUp` je Test eine weitere Wurzel und warf sie wieder weg. **Wird die letzte Tk-Wurzel eines Prozesses zerstört, lässt sich Tcl unter Windows nur noch unzuverlässig neu hochfahren:**

```text
TclError: Can't find a usable init.tcl in the following directories: {…\tcl\tcl8.6}
couldn't read file "…/tcl8.6/init.tcl": No error
```

Welcher Test es trifft, ist Zufall — beim ersten Mal `test_beschriftung_folgt_der_sprache`, beim Nachstellen `test_knopf_existiert_mit_richtiger_beschriftung`. Genau das erzeugte das flatterhafte Bild.

Die Wurzel wird jetzt angelegt und **behalten**, die Oberfläche einmal je Klasse gebaut statt dreimal. Sechs Läufe hintereinander grün, nebenbei von 4–5 s auf 3,1–3,7 s.

Der Kommentar, der an dieser Stelle stand, zeigt dieselbe Fehlerfamilie von der anderen Seite: `image "pyimageNNN" doesn't exist`, damals umschifft mit einem Tausch von `tk._default_root` statt an der Ursache.

### 2. Ein fest erwarteter deutscher Text

`test_knopf_existiert_mit_richtiger_beschriftung` verlangte wörtlich `"BENUTZERHANDBUCH"`. Die Oberfläche übernimmt beim Bau aber die **gemerkte** Sprache aus der Konfiguration. Nachgestellt, indem `language` kurz auf `en` gesetzt wurde:

| Einstellung | Ergebnis |
| --- | --- |
| `language=de` | 17 grün |
| `language=en` | **1 Fehlschlag** |

Geprüft wird jetzt gegen `translate(app._current_language, "titlebar.manual")` — beide Sprachen grün.

### 3. Ein zurückgezogenes Fenster und das Hintergrundbild des Nutzers

Drei Tests in `test_beschriftung_flackern.py` übersprangen sich selbst, wenn gerade keine Beschriftung abgebildet war oder kein Hintergrundbild im Zwischenspeicher lag. In einem Gesamtlauf kamen dadurch 6 statt 3 Übersprungene heraus.

`winfo_ismapped()` meldet `False`, solange die Wurzel zurückgezogen ist — und andere Testdateien ziehen die gemeinsame Wurzel zurück. Das Fenster wird jetzt vorgezeigt (unsichtbar durch `-alpha 0.0`) und der vorgefundene Zustand am Ende wiederhergestellt. Für den Flackertest wird notfalls ein beliebiges mitgeliefertes Hintergrundbild geladen, statt sich zu überspringen — er prüft das Zeichnen, nicht die Bildauswahl.

| Prüfung | vorher | nachher |
| --- | --- | --- |
| einzeln | 3 grün, 3 übersprungen | **6 grün** |
| hinter `test_fensterlayout` | übersprang | 37 grün |
| hinter `test_kartenzeilen` | übersprang | 26 grün |

## Zwei Wege, die verworfen wurden

Beide waren naheliegend und beide messbar schlechter:

**Die Testklasse auf eine geteilte Wurzel umbauen, ohne das `destroy()` anzufassen** — machte es schlimmer: konstant drei Fehler statt gelegentlich einem.

**In `setUp` auf Deutsch stellen** — kippte `test_knopf_steht_links_vom_sprachknopf`. Dabei kam heraus, dass `_apply_language()` die Titelleiste **neu packt** und damit die Reihenfolge ändert, auf die jener Test sich stützt.

## Nachgeprüft

Drei vollständige Läufe nach der Korrektur, jeweils identisch:

```text
Lauf 7:  1155 grün, 3 übersprungen   2:39
Lauf 8:  1155 grün, 3 übersprungen   2:47
Lauf 9:  1155 grün, 3 übersprungen   2:30
```

Die drei Übersprungenen sind namentlich die absichtlichen: zwei Integrationstests hinter Umgebungsvariablen (`RUN_FFPKG_INTEGRATION`, `RUN_FFPKG_648MB_INTEGRATION`) und einer, der nur auf Dateisystemen mit Groß- und Kleinschreibung gilt. Über neun aufgezeichnete Gesamtläufe hinweg kein Fehlschlag.
