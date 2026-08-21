# Release Notes – v1.8.74

**Datum:** 21.08.2026
**Vorgänger:** v1.8.73

Ein Nutzer mit einer Firewall auf dem Mac hat gefragt, warum sein Konverter sich zu `store.playstation.com` verbinden will. Die Antwort war unangenehm: weil er das schon immer tat, ungefragt, und niemand es sehen konnte.

---

## Der Befund

Fehlten in einem Backup **Titel, Publisher oder Kategorie**, hat das Programm sie nachgeschlagen. Ohne Rückfrage, ohne Schalter, ohne Spur in der Oberfläche. Nachgestellt mit abgefangenen Verbindungen:

| Fall | Verbindungen |
| --- | --- |
| Metadaten vollständig | 0 |
| Publisher + Kategorie fehlen | **4** |
| Titel gleich der Title-ID | **1** |

Insgesamt gingen **sechs Stellen** von selbst hinaus:

| Stelle | Ziel |
| --- | --- |
| `_fetch_psstore_meta` | store.playstation.com, drei Regionen |
| `_resolve_title_id_from_store_search` | store.playstation.com |
| `_fetch_patch_page_meta` | prosperopatches.com / orbispatches.com |
| `_fetch_patches_async` | dieselben, automatisch beim Öffnen der Spiel-Info |
| `_download_cover_online` | cdn.prosperopatches.com |
| `_resolve_title_id_from_patch_search` | **duckduckgo.com** |

Die letzte ist die unangenehmste: Dorthin ging nicht die Title-ID, sondern der ausgeschriebene Spielname.

Warum es jetzt erst auffiel: Der Nachschlag greift nur bei unvollständigen Metadaten. Ein aus PKG gebautes **PS4-Abbild** bringt Publisher und Kategorie oft nicht mit – und genau damit hat der Nutzer zuletzt gearbeitet. Unter Windows fragt nichts nach; auf dem Mac meldet die Firewall jede Verbindung.

## Was sich ändert

Der Abruf ist jetzt eine **Handlung**, kein Automatismus. Fehlt etwas, erscheint in der Spiel-Info ein Knopf:

```text
[ Fehlende Angaben online nachschlagen ]
```

Erst der Klick öffnet ein Zeitfenster, holt Titel, Publisher, Kategorie und Titelbild – und schließt es sofort wieder. Fehlt nichts, erscheint der Knopf gar nicht.

Für alle, die es dauerhaft wollen, gibt es in den Einstellungen den Abschnitt **METADATEN AUS DEM NETZ** mit einem Kästchen. Ab Werk ist es leer, und darunter stehen die gefragten Dienste beim Namen.

Der lokale Zwischenspeicher bleibt unangetastet: Einmal geholte Angaben liegen 30 Tage auf der Platte und kosten keine zweite Verbindung. Auch bei abgeschaltetem Nachschlag wird er weiter gelesen – er liegt lokal.

**Nicht betroffen:** Aktualisierungsprüfung, Download-Verwaltung, Verbindungen zur PS5 und der Nachschlag bei defekter `param.json`. Die laufen alle erst auf Knopfdruck, teils mit eigener Rückfrage.

## Was das für eine Firewall bedeutet

Die Meldung selbst lässt sich aus dem Programm heraus nicht verhindern – Little Snitch und Verwandte fragen bei jeder ausgehenden Verbindung ohne Regel. Was sich geändert hat: Sie kommt nur noch, wenn du den Knopf drückst. Erlaubst du sie dann einmal dauerhaft statt „Einmal", bleibt es still, und das Programm geht trotzdem nur hinaus, wenn du es anstößt.

Ein Hinweis dazu: Das macOS-Bündel wird **ad-hoc signiert** (`codesign --sign -`), weil kein Apple-Entwicklerzertifikat vorliegt. Deshalb steht in der Firewall-Meldung „Der Prozess hat keine Code-Signatur" – und deshalb kann eine gespeicherte Regel nach einem Update ungültig werden.

## Das PS4-Fenster sagt jetzt, wohin das Abbild gehört

Ein umrandeter Kasten über „ABBILD ERSTELLEN", mit dem, was an der Konsole gemessen wurde (FW 12.00, ShadowMount+ v1.7alpha6):

| | |
| --- | --- |
| ✓ | Direkt nach `/mnt/usb0/` – Unterordner werden nicht durchsucht. Ein Abbild in `/mnt/usb0/ps4ffpsc/` wird nie gefunden. |
| ✗ | Nicht nach `/data/homebrew` oder `/data/etaHEN/games` – von dort gestartet gibt es einen Kernel Panic, die PS5 schaltet ab. |
| ! | Danach bleibt ein leerer Eintrag zurück; erst die Kachel auf der PS5 löschen, sonst wird das Abbild auch am richtigen Ort nicht mehr gefunden. |

Nachgewiesen an `image_index.bin` auf der Konsole: Vor dem Verschieben kannte der Index einen einzigen Abbildpfad und null Einträge mit `/mnt/usb0`. Nach dem Verschieben in die Wurzel wurde die Datei beim nächsten 15-Sekunden-Durchlauf eingehängt und registriert.

**Der bisherige Hinweistext desselben Fensters empfahl ausgerechnet `/mnt/usb0/ps4ffpsc/`** – also den Ordner, in dem nichts gefunden wird. Ein Test verhindert jetzt, dass dieser Pfad je wieder als Empfehlung auftaucht.

## Zwei Fehler, die beim Einbauen sichtbar wurden

**Der Kasten sprengte das Fenster.** Erster Entwurf: 1235 px Höhe nötig, möglich sind auf einem 1080er Bildschirm 1000. EINLESEN, ABBILD ERSTELLEN, ABBRECHEN und Schließen standen außerhalb. Texte gestrafft, Liste 7→4 Zeilen, Protokoll 8→4 Zeilen: jetzt 992 von 992. Zusätzlich wird die Knopfreihe mit `before=` **vor** dem dehnbaren Körper gepackt – sonst nimmt der sich den ganzen Platz.

**Der Nachschlag-Knopf war unsichtbar.** `winfo_manager` meldete „pack", `winfo_ismapped` meldete False. Nachträgliches `pack()` hängt ein Element ans **Ende** des Containers, und dort war kein Platz mehr. Jetzt mit festem Bezug (`before=size_bar`). Dieselbe Falle in zwei verschiedenen Fenstern an einem Tag.

Dazu abgesichert: Wird die Spiel-Info während des Nachschlags geschlossen, wirft `root.after()` aus dem Arbeitsfaden „main thread is not in main loop". Das wird jetzt abgefangen.

## Ein Fehler aus v1.8.73

Die obere Bedienzeile ragte bei der kleinsten Fenstergröße um **einen Pixel** über die Karte hinaus. Die Bildlaufleiste der Inhaltsfläche ist bei `WINDOW_MIN_HEIGHT` immer sichtbar und nimmt 15 px – die fehlten in der Reserve:

```text
1230x1050   Karte 657   Leiste aus   Zeile endet 643   passt
1230x700    Karte 642   Leiste an    Zeile endet 643   über 1 px
```

`WINDOW_MIN_WIDTH` steht deshalb auf 1245 statt 1230. Der Test prüft ab sofort beide Fensterhöhen.

## Nachgeprüft

| Woran | Ergebnis |
| --- | --- |
| Nachschlag abgeschaltet | 0 Verbindungen in allen drei Fällen |
| Knopf gedrückt | 5 Verbindungen, danach wieder gesperrt |
| Vollständige Metadaten, Schalter an | 0 Verbindungen |
| Zwischenspeicher | wird auch bei abgeschaltetem Nachschlag gelesen |
| PS4-Fenster, deutsch / englisch | 992 / 972 px – passt genau |
| Karte bei Mindestbreite, Leiste an | 643 von 657 px |

Neu ist `test_metadaten_online.py` mit 14 Prüfungen: jede der sechs Netzstellen fragt den Schalter, die Sperre steht **vor** dem ersten Holen, der Zwischenspeicher bleibt erlaubt, die Texte nennen die Dienste beim Namen, und je ein Test gegen die beiden oben beschriebenen Fehler. Dazu vier neue Prüfungen im PS4-Testmodul und eine, dass die Knöpfe dort erreichbar bleiben.

204 Tests grün.
