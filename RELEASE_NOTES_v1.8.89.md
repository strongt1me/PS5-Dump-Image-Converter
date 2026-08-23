# PS5 Dump & Image Converter v1.8.89

**23.08.2026**

Eine Aufräum-Ausgabe. **Am Verhalten ändert sich nichts** — entfernt wurde nur,
was ohnehin nie ausgeführt wurde.

## 95 Zeilen, die nie liefen

Der Programmcode wurde gezielt nach totem Code durchsucht: Anweisungen hinter
einem `return`, doppelt definierte Funktionen, und vor allem Funktionen, die
niemand aufruft.

| Was | Umfang |
| --- | --- |
| Fünf Funktionen ohne einen einzigen Aufruf | 86 Zeilen |
| Eine Rechnung, deren Ergebnis nie gelesen wird | 8 Zeilen |
| Reste einer ausgebauten Geschwindigkeitsanzeige | 3 Zeilen |

Mit den Funktionen fiel weg, was nur ihretwegen existierte: eine Zeichenliste
zum Bereinigen von Ordnernamen und eine Fensterreferenz.

Nicht gefunden wurde — erfreulicherweise — **kein** unerreichbarer Code und
**keine** doppelt definierte Funktion.

### Die Rechnung, die bei jedem Fortschritt lief

Der interessanteste Fall: In der Fortschrittsanzeige wurde ein Wert an fünf
Stellen berechnet und an **keiner einzigen** gelesen. Die Anzeige aktualisiert
sich während einer Umwandlung fortlaufend — die Rechnung lief also ständig
mit, ohne je ein Ergebnis zu liefern.

Der erklärende Kommentar an dieser Stelle ist geblieben: Er beschreibt, warum
der rohe Teilfortschritt bewusst nicht an den Balken weitergereicht wird —
sonst spränge die Anzeige bei jedem Phasenwechsel auf 0 % zurück. Diese
Begründung ist weiterhin wichtig; nur der Verweis auf die entfernte Variable
wurde umformuliert.

## Was bewusst stehen blieb

Nicht jede Funktion ohne Aufruf ist tot:

* **Behandlung von Netzwerkanfragen** — wird vom System gerufen, nicht vom
  Programm.
* **Abfragen an den Paket- und SELF-Leser** — gehören zur Schnittstelle dieser
  Bausteine.
* Ein einzeiliger Zugriff auf den Fortschrittswert, plausibel als
  Schnittstelle gedacht.

## AMPR-Index-Builder: „app0“ heißt jetzt „Dump“

Im Fenster **AMPR-Index-Builder** stand an drei Stellen "app0" – die
Beschriftung des Ordnerfelds, der Titel des Auswahldialogs und die
Begrüßung im Protokoll. Gemeint war immer der Dump-Ordner, und genau so
heißt es jetzt auch.

Unverändert bleibt die Meldung "Durchsuche /app0 auf der PS5": Dort ist
`/app0` der tatsächliche Pfad auf der Konsole, keine Beschriftung.


## Ein irreführender Kommentar

Ein Zwischenspeicher trug einen Kommentar, der den falschen Verbraucher
nannte. Beim Aufräumen führte das beinahe dazu, ihn zu entfernen — obwohl er
gebraucht wird: Er liefert die letzten 60 Protokollzeilen an den
**Diagnosebericht**.

Der Fehler wurde vor dem Speichern bemerkt und zurückgenommen; der Kommentar
nennt jetzt den richtigen Verbraucher. Genau dafür sind solche Kommentare da —
dieser hat in die Irre geführt.

## Geprüft

**1300 Tests** laufen durch, unverändert gegenüber v1.8.88 — was zu erwarten
war, denn entfernter toter Code kann keine Prüfung beeinflussen.

Die eingebaute Darstellungsdiagnose meldet keine Auffälligkeit: 90 vermessene
Bedienelemente, Fenster, Beschriftungen, Bilder und Skalierung passen
zusammen.

Dass die entfernten Stellen wirklich tot waren, wurde nicht über Textsuche
entschieden, sondern über den Syntaxbaum — inklusive Aufrufen aus Tests und
solchen über Zeichenketten.
