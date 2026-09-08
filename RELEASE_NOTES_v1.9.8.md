## Neu: AMPR EMU kann die Spieldateien packen

Neben der Klappliste für die AMPR-Fassung steht eine zweite zur Wahl:
**Normal** oder **Neue Methode (Asset-Pack)**.

*Normal* ist der bisherige Weg — die Spieldateien bleiben einzeln liegen.

Bei der *neuen Methode* wandern sie zusätzlich in gepackte Bänder
(`ampr_assets-*.pak`), die der AMPR EMU ab Fassung 0.4.2.1 blockweise mit LZ4
liest. Das spart Platz und Dateideskriptoren. Wer sie wählt, muss nichts
weiter tun: Profil schreiben, packen, prüfen und die Bänder in den Spielordner
legen läuft in einem Zug.

**Geprüft wird gegen die Quelle, nicht nur gegen sich selbst.** Jeder
zurückgerechnete Block wird Byte für Byte mit der Originaldatei verglichen.
Erst wenn das für jede gepackte Datei stimmt, wird etwas übernommen. Eine
Prüfung ohne diesen Vergleich sagt nur, dass die Bänder in sich stimmig sind —
nicht, dass sie den Spielinhalt tragen.

**Die Originale bleiben liegen.** Das Werkzeug könnte sie entfernen, aber
nicht hier: Ob ein Spiel wirklich jede Datei über den AMPR EMU liest, zeigt
erst ein Lauf auf der Konsole. Manche Titel lesen über `mmap` daran vorbei,
und das fällt am PC nicht auf.

Zwei Voraussetzungen nennt das Programm von selbst:

- Die neue Methode braucht eine **pack-fähige Fassung** (`test-pack` oder
  `test-debug-pack`). Eine `test-nopack`-Fassung findet die Bänder nicht.
- Fehlt das Packwerkzeug oder das LZ4-Modul, fällt die Auswahl **sofort bei
  der Wahl** sichtbar auf *Normal* zurück — nicht erst nach einer halben
  Stunde Arbeit.

---

## Der Fehler, den der erste Probelauf zutage brachte

Systemdateien dürfen nie in ein Band: `eboot.bin`, `sce_sys`, die Module,
alles Ausführbare. Das Ladeprogramm der Konsole liest sie, bevor der AMPR EMU
überhaupt geladen ist.

Die Ausschlussliste stand von Anfang an im Profil — und griff trotzdem nicht.
Ein Probelauf mit acht Dateien packte `eboot.bin` mit:

    Lose: 1
       lose: sce_sys/param.sfo
    (eboot.bin fehlt — also gepackt)

Der Grund ist ein Detail der Mustersprache: `**/eboot.bin` verlangt
mindestens ein Verzeichnis davor und trifft die Datei im Wurzelverzeichnis von
`/app0` deshalb nicht. Genau dort liegt sie. `sce_sys/**` griff, `**/eboot.bin`
nicht.

Auf der Konsole wäre das nicht als Fehlermeldung aufgefallen, sondern als
Spiel, das nicht mehr startet. Jetzt steht jeder Name doppelt in der Liste —
mit und ohne `**/` — und ein Test packt einen kleinen Baum wirklich durch und
sieht nach, was lose geblieben ist.

---

## Neu: Der Backport sagt vorher, was fehlen wird

Bisher zeigte sich erst auf der Konsole, ob ein herabgesetztes Spiel startet.
Wenn nicht, ohne brauchbare Meldung.

Wer einen entpackten Firmware-Bestand hinterlegt, bekommt die Antwort jetzt
vor dem Umschreiben ins Protokoll — wie viele Funktionen auf der Zielfirmware
fehlen und aus welchen Bibliotheken sie stammen. Eingestellt wird der Bestand
über `backport_firmware_referenz`: ein Ordner mit Unterordnern je Fassung
(`7.61`, `9.40`, …). Ohne ihn bleibt alles wie bisher.

Ein Befund ist **kein Abbruchgrund**. Genau diese Lücken sollen die
Ersatzbibliotheken schließen; ob sie es tun, sagt die zweite Prüfung nach dem
Kopieren.

An zehn Spielen nachgemessen, wie groß die Lücke je Zielfirmware ist:

| Zielfirmware | fehlende Funktionen |
| --- | --- |
| 7.01 | 24 |
| 8.60 | 13 |
| 9.40 | 9 |
| 11.00 | keine |

Fast alles davon steckt in `libSceAgc` — und es sind über die Spiele hinweg
dieselben Funktionen. `libSceAgc/dbOlWdppb4o` fehlte bei sechs von acht
Titeln, `vieBRwlh1Lw` bei vier.

Der Vergleich läuft dabei auf Ebene einzelner Funktionen, nicht ganzer
Bibliotheken. Ein Bibliotheksvergleich taugt dafür nicht: Er meldet für
Firmware 12 dieselbe Liste wie für Firmware 7, obwohl ein Spiel mit SDK 10 auf
Firmware 12 läuft. Namen wie `libScePosix` oder `libSceAudioOut2` haben gar
keine eigene Datei — sie stecken in `libkernel` beziehungsweise einem
Nachbarmodul.

---

## Geändert: Die Firmware-Auswahl beim Backport richtet sich nach dem Bestand

Wählbar waren fest 4 bis 7. Diese Liste stand im Programm, obwohl daneben
schon alles für höhere Stände vorbereitet war.

Jetzt wird nachgesehen. Wer einen eigenen Bibliothekssatz als
`Backport_Fakelibs/8/fakelib/` ablegt, kann Firmware 8 danach auswählen — am
Programm ist dafür nichts zu ändern.

Mitgeliefert werden weiterhin nur 4 bis 7. Der Grund ist rechtlich, nicht
technisch: PS5 BACKPORK KITCHEN führt in `FAKELIBS_SETUP.md` die Firmware 1.x
bis 10.x als unterstützt und schreibt dazu ausdrücklich, dass die
Bibliotheken nicht weitergegeben werden dürfen.

Ergänzt wurden außerdem die SDK-Kennungen für Firmware 11 und 12. Sie sind
aus echten Firmware-Modulen gelesen und je Stand gegen sechs Module
gegengeprüft, nicht hochgerechnet:

| Firmware | PS5-SDK | PS4-SDK |
| --- | --- | --- |
| 11.00 | `0x11000043` | `0x12590001` |
| 12.00 | `0x12000043` | `0x13090001` |

Die Werte für 1 bis 10 bleiben unverändert. Dieselbe Messung liefert für sie
andere Baunummern als die bisherige Tabelle — kein Widerspruch, denn der
Modulkopf einer Systembibliothek trägt die Fassung, mit der **sie** gebaut
wurde, nicht den Wert, den ein herabgesetztes Spiel tragen muss. Die
bisherigen Werte sind in der Szene erprobt, die gemessenen sind es nicht.

---

## Behoben: Die Testsammlung lief in fremde Quellbäume

`pytest` sammelte vom Projektstamm aus alles ein, was wie ein Test aussieht —
auch in mitliegenden Fremdbäumen. Unter `PS5 SDK usw/llvm-project-…` liegt ein
LLVM-Hilfsskript, das beim bloßen Import `sys.exit(1)` aufruft. Der Lauf endete
dadurch mit einem internen Abbruch nach 102 Fehlern, **ohne einen einzigen
Projekttest auszuführen**.

Ein zweiter Fund kam dazu: Unter `.claude/worktrees/` liegt eine ältere
vollständige Kopie des Projekts. `pytest` stellte deren Ordner vorn in den
Suchpfad, sodass `import ps5_validator` gegen die alte Kopie auflöste — 147
Testdateien brachen mit `ImportError` ab, obwohl im Stamm alles vorhanden war.

Beides regelt jetzt eine `pytest.ini`. Statt eines Abbruchs werden 2528 Tests
gesammelt.
