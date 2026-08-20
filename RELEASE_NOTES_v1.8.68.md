# Release Notes – v1.8.68

**Datum:** 20.08.2026
**Vorgänger:** v1.8.67

Diese Ausgabe bringt eine Funktion: AMPR EMU und BACKPORT lassen sich beim Erstellen eines Backups ankreuzen, statt sie hinterher über ein eigenes Fenster nachzuziehen.

---

## Die neue Zeile

In der Pfad-Karte, rechts neben der Prüfstufe, stand bisher die Beschriftung „PRÜFUNG NACH DEM PACKEN". Sie ist entfallen – die Zeilenüberschrift nennt die Prüfung ohnehin. An ihrer Stelle stehen jetzt:

```
☑ AMPR EMU  [0.3.5.1 no debug ▾]  ☑ PlayGo    ☑ BACKPORT  [7 ▾]
```

- **AMPR EMU** – legt die gewählte `libSceAmpr.sprx` in den fakelib-Ordner und baut `ampr_emu.index` neu. Zwanzig Versionen stehen zur Wahl (0.2.6 … 0.3.5.1, je „debug"/„no debug").
- **PlayGo** – eigenes Häkchen, nicht vorausgewählt. `libScePlayGo.sprx` stammt aus einem anderen Projekt (pgo_stub) und wird nur gebraucht, wenn ein Titel Inhalte als fehlend behandelt.
- **BACKPORT** – setzt die SDK-Angaben aller Programmdateien auf die gewählte Firmware herab (4/5/6/7) und legt die passenden Ersatzbibliotheken dazu. Angehoben wird nie.

Die Auswahllisten bleiben stehen, wenn ihr Kästchen aus ist, und werden nur gesperrt: Sie sitzen in einer `place`-Kette, ein Ein- und Ausblenden würde alles rechts davon verrutschen lassen.

---

## Wo es greift

Beide Integrationen arbeiten **auf einem Dump-Ordner** – nie auf einem fertigen Abbild. Das ist keine Einschränkung, sondern der einzige verlässliche Weg: Jedes Zielformat entsteht aus einem Ordner, und bei Container-Quellen liegt der ohnehin schon ausgepackt im Temp-Verzeichnis.

Abgedeckt sind damit alle zehn Konvertierungswege:

| Weg | Ordner-Herkunft |
| --- | --- |
| Ordner → .ffpfsc/.ffpfs, .exFAT, .ffpkg | Quellordner des Benutzers |
| .ffpfsc → .exFAT, .ffpkg, Dump-Ordner | Temp (ausgepackt) |
| .exFAT → .ffpkg, Dump-Ordner | Temp |
| .ffpkg → .exFAT, .ffpkg | Temp |

Ein Test prüft für jeden dieser Wege, dass er durch denselben Einbau geht – genau die Lücke, die beim Auspacken in dieser Woche dreimal auftrat.

### Reihenfolge

Erst der Backport, dann der AMPR EMU. Beide schreiben in denselben fakelib-Ordner; liefe der Backport zuletzt, überschriebe er die eben eingebaute AMPR-Bibliothek. Ein Test hält das fest, indem er die Dateigröße der eingebauten Bibliothek gegen die gewählte Version prüft.

### Arbeitskopie

Ist die Quelle ein Dump-Ordner (Aufgabe 1), fragt das Programm vor dem Start:

- **Ja** – es entsteht eine Arbeitskopie im Temp-Ordner, der Quellordner bleibt unberührt. Kostet einmal denselben Platz.
- **Nein** – gearbeitet wird direkt im Quellordner. Ersetzte AMPR-Dateien bleiben als `.orig` liegen.

Bei Container-Quellen entfällt die Frage.

### Doppelschutz

Mehrstufige Wege rufen einander auf: `.ffpfsc → .ffpfs` läuft über den Dump-Ordner, `.ffpfsc → .ffpkg` ebenso. Ein Merker sorgt dafür, dass der Einbau nur einmal je Aufgabe läuft – sonst käme die Frage nach der Arbeitskopie zweimal, und der zweite Durchgang arbeitete auf einem Ordner, in dem alles schon steht.

---

## Zwei Fehler nebenbei behoben

**Die Versionsliste sortierte falsch.** `0.3.5` stand vor `0.3.5.1`. Beim absteigenden Sortieren gewinnt sonst die *kürzere* Nummer, weil Python bei gleichem Anfang das kürzere Tupel als kleiner ansieht – als „neueste Version" wurde also die ältere vorausgewählt. Der Schlüssel wird jetzt auf feste Länge aufgefüllt. **Das galt genauso für Aufgabe 7**, den AMPR-EMU-Manager.

**PlayGo wäre nie gefunden worden.** Gesucht wurde nach derselben Versionsnummer wie beim AMPR-Modul. Die gibt es dort nie: `libScePlayGo.sprx` stammt aus einem eigenen Projekt und zählt getrennt – mitgeliefert ist 0.5 als „log"/„nolog". Jetzt entscheidet die Variante statt der Nummer.

---

## Prüfung

- **980 Tests grün** (3 übersprungen), 14/14 Quality-Tests.
- Neu: `test_integration_beim_erstellen.py` mit 14 Fällen – Sortierung, PlayGo-Zuordnung, Einbau, Reihenfolge, Arbeitskopie, Doppelschutz und die Abdeckung aller zehn Wege.
- An einem echten Ordner durchlaufen: 6 Ersatzbibliotheken kopiert, `libSceAmpr.sprx` (0.3.5.1) und `libScePlayGo.sprx` eingebaut, `ampr_emu.index` mit 2517 Einträgen neu gebaut.

**Offen:** Der Backport hat im Testdump 0 Dateien herabgesetzt – die enthalten keine echten ELFs mit SDK-Angabe. Die Patch-Logik selbst deckt `test_backport.py` ab; die Kombination „echtes Spiel + Integration beim Erstellen" steht als Praxistest noch aus.
