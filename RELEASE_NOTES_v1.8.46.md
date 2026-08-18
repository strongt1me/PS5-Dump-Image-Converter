# PS5 Dump & Image Converter v1.8.46 – Release Notes

## Zweck dieses Releases

Die Artefakte im Protokollfeld sind behoben – diesmal an ihrer wirklichen Ursache. v1.8.44 und v1.8.45 haben beide die **Eingangsseite** behandelt: Wie die Ausgabe der Engines in Zeilen zerlegt wird. Beide Reparaturen waren richtig, aber sie konnten den Fehler nicht beheben, weil er nicht dort saß. Eine dritte Bildschirmaufnahme zeigte ihn unverändert.

---

## Die Ursache: eine Eigenheit von Tk

Ein Fortschrittsbalken soll sich fortschreiben, nicht stapeln. Dafür wird die stehende Balkenzeile entfernt und die neue eingesetzt:

```python
ansicht.delete(anfang, tk.END)
ansicht.insert(tk.END, neue_zeile)
```

Ein `tk.Text` hält immer **genau einen** abschließenden Umbruch vor und lässt ihn nicht löschen. Ein Löschen bis `END` nimmt deshalb der **davorstehenden** Zeile ihren Umbruch mit. Nachgemessen an einem echten Feld:

| | `end-1c` | Inhalt |
| --- | --- | --- |
| vor dem Löschen | `3.0` | `>>> Schritt 1 / 2: ...\n[####----]  50% scan\n` |
| nach dem Löschen | **`1.35`** | `>>> Schritt 1 / 2: ...` |

Spalte 35 statt 0: Das Feld endet mitten in der Zeile. Der nächste Einschub läuft hinten dran, und es entsteht genau das, was in allen drei Aufnahmen zu sehen war:

```
>>> Schritt 2 / 2: inneres PFS -> komprimierter Aussencontainer...[####] 100% compress
```

## Und es kam Schlimmeres dazu

Diese verklebte Zeile enthält einen Balken. Beim nächsten Balken derselben Phase gilt sie deshalb als Balkenzeile – und wird **vollständig gelöscht, samt der Meldung darin**.

Das erklärt den Teil der Aufnahme, der wie ein Anzeigefehler aussah: Der Parameterblock von mkpfs endete bei `Encrypted: no`, alles darunter fehlte. Die Zeilen waren nicht ausgeblendet, sie waren vernichtet. An einem echten Lauf gemessen – gleiche Aufgabe, gleiches Spiel:

| | v1.8.45 | v1.8.46 |
| --- | --- | --- |
| Zeilen im Feld | 31 | **120** |
| verklebte Zeilen | 1 | **0** |
| verschluckte Sachzeilen | **72** | 0 |

Unter den 72 verlorenen Zeilen war der gesamte Parameterblock: Quellpfad, Zielpfad, Blockgröße, Inode-Breite, PFS-Modus, der vollständige mkpfs-Aufruf.

---

## Die Reparatur

Zwei Hilfsfunktionen, beide dort, wo ins Feld geschrieben wird:

| Funktion | Aufgabe |
| --- | --- |
| `_log_letzte_zeile_entfernen()` | Nimmt die stehende Balkenzeile weg – wie bisher, jetzt an einer Stelle statt an zwei |
| `_log_auf_zeilenanfang()` | Schließt eine offene Zeile, **bevor** irgendetwas eingeschoben wird |

`_log_auf_zeilenanfang()` läuft in **beiden** Schreibwegen vor jedem Einschub. Offen ist eine Zeile in zwei Fällen: nach einer Meldung ohne Umbruch und nach dem Löschen oben. Zusätzlich gehen Meldungen jetzt immer mit Umbruch ins Feld.

Das Verhalten, das erwünscht ist, bleibt: Ein Balken schreibt sich fort, statt sich zu stapeln, und bei einem Phasenwechsel (`scan` → `write`) bleibt der alte als Beleg stehen.

---

## Warum zwei Releases daran vorbeigelaufen sind

Die Tests zum Protokollfeld arbeiteten ausschließlich mit **Nachbildungen** – Zeichenketten, die den Zeilentrenner nachbauen. Eine Nachbildung kann diese Index-Semantik nicht zeigen: Sie ist eine Eigenheit von Tk, nicht der Zerlegung. Alle 16 Tests waren grün, während der Fehler unverändert im Programm stand.

`test_protokollfeld.py` prüft jetzt **28 Fälle**, davon 9 an einem **echten `tk.Text`**. Gegenprobe gemacht: Mit dem alten Verhalten fällt `test_fortschreibender_balken_frisst_die_meldung_nicht` mit genau dem Symptom der Aufnahme – übrig bleibt allein `['[########] 100% write']`, die Meldung ist weg.

Festgehalten ist auch die Falle selbst (`test_loeschen_bis_ende_laesst_die_zeile_offen`), damit ein späterer Umbau nicht wieder darauf tritt.

**Merke: Wo Tk-Indizes im Spiel sind, prüft nur ein echtes Widget.**

---

## Tests

**46 Testdateien grün**, `test_build_ready.py` zusätzlich 8/8 als Build-Freigabe.

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.46.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.46.sha256` | Prüfsummen aller Quelldateien |
