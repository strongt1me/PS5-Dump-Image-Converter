Diese Fassung bringt keine neuen Funktionen. Sie behebt, was seit v1.9.7 bei
den Aufgaben 1–8 den Eindruck erweckt hat, das Programm sei kaputt.

**Vorweg, weil es die Ausgangsfrage war:** Die Aufgabenwege selbst waren
nicht defekt. Ein methodenweiser Vergleich v1.9.6 gegen v1.9.12 zeigt, dass
`_mode_pack_folder`, `_mode_pack_file`, `_mode_ffpkg_to_ffpfsc`,
`_mode_exfat_to_folder` und `_mode_dump_validator` im Kern **unverändert**
sind – geändert wurden dort nur Texte. Kaputt war, was der Anwender **sieht**,
und das war schlimm genug: Es sah in jedem größeren Lauf nach Absturz aus.

## Der Fortschrittsbalken sprang zwischen 0 % und 100 %

Der schwerste Fund. Er steht in den Diagnoseberichten des Anwenders, aus
seinen eigenen Läufen:

| Version | Lauf | Befund |
| --- | --- | --- |
| v1.9.6 | 207 s | keine Auffälligkeit |
| v1.9.12 | 45 s | 26 Rücksprünge, bis 2,6 % → 0,0 % |
| v1.9.12 | 1769 s | 284 Rücksprünge, bis 100,0 % → 0,0 % |
| v1.9.12 | 4453 s | **567 Rücksprünge**, bis 100,0 % → 0,0 % |

Zwei Arbeitsschritte, die es in v1.9.6 noch nicht gab, schrieben ihren
eigenen Prozentwert direkt auf den Balken: das Anlegen der **Arbeitskopie**
(wenn AMPR EMU oder BACKPORT angehakt ist) und das **Packen der
Asset-Bänder**. Achtzig Millisekunden später setzte die reguläre Anzeige
wieder den Gesamtwert – der Balken zappelte zwischen beiden.

Die Folge war schlimmer als der Fehler: Weil sich weder Balken noch
Statuszeile bewegten, hielt die eingebaute Aufhänger-Erkennung das für einen
Absturz und schrieb nach zwei Minuten einen Stapelabzug als **Fehler** ins
Protokoll – mitten in einem völlig normalen Lauf. Am 10.09.2026 schon bei
einem 5,6-GB-Titel nachgestellt: Meldung nach genau 120 Sekunden. Bei einem
150-GB-Titel dauert allein die Arbeitskopie rund eine Stunde bei scheinbar
0 %. Wer da abbricht, bekommt kein Backup.

Beide Schritte rechnen ihren Anteil jetzt in den Gesamtfortschritt um und
tragen ihre Zahlen zusätzlich in die Statuszeile.

## „Code 1 Disc-Full" war zweimal geraten

Der Satz stammt aus zwei Zeilen, die zusammen erscheinen und sich wie ein
Befund lesen:

> `[WARNUNG] mkpfs beendet mit Exit-Code 1`
>
> Die Konvertierung ist fehlgeschlagen. Details stehen im Konsolen-Fenster
> (z. B. mkpfs Exit-Code oder **Disk-Full-Meldung**).

Die zweite Zeile nennt zwei **Beispiele**. Geprüft war keines davon – den
freien Platz hatte das Programm nie nachgesehen. Jetzt steht dort nur, was
tatsächlich gemessen wurde:

> Gemessen wurde:
> - Die Packmaschine endete mit Rückgabewert 1.
> - Die Ausgabeprüfung meldet: Ausgabepfad existiert nicht.

Der freie Platz erscheint dort nur, wenn er wirklich knapp ist – dann mit
Pfad und Zahl.

## Die Packmaschine verdeckte den eigentlichen Fehler

Geht beim Packen etwas schief, räumt MkPFS seine halbfertige Datei weg und
reicht den ursprünglichen Fehler weiter. Ihr eigener Kommentar sagt das:
*„Re-raise the original exception … so callers observe the original
traceback."* Beim Wegräumen fing sie allerdings nur „Datei ist schon weg" ab.

Unter Windows ist ein anderer Fall der Normalfall: **„Datei ist noch
belegt"** – ein Virenscanner liest sie, der Suchindex greift zu. Diese
Meldung ersetzte dann den echten Fehler. Am 10.09.2026 in Aufgabe 3 genau so
gemessen: gemeldet wurde ein `PermissionError` beim Aufräumen, die wirkliche
Ursache stand nur noch als Fußnote im Stapel.

Sieben Stellen umgestellt, in `MkPFS-1.0.0/UPSTREAM.md` als fünfte Abweichung
von der Vorlage dokumentiert.

## Eine belegte Zieldatei bricht den Lauf jetzt sofort ab

Vor jedem Packlauf räumt das Programm eine alte Zieldatei weg. Ging das
nicht, stand nur eine Warnung im Protokoll und der Lauf machte weiter – bis
er Minuten später mit einer Meldung scheiterte, die mit der Ursache nichts zu
tun hatte. Genau so im Protokoll gesehen: Zwei Zeilen vor dem
`PermissionError` stand bereits „Altes Zielartefakt konnte nicht entfernt
werden", ungehört.

Jetzt wird sechsmal versucht – Windows gibt eine Datei meist nach
Sekundenbruchteilen wieder frei – und sonst klar abgebrochen, mit Dateiname
und den üblichen Ursachen.

## Der eingestellte Arbeitsordner wurde überschrieben

Ein älterer Fehler, der genau die Sorte Ärger macht, die man nicht zuordnen
kann. Sechs Arbeitsschritte legen ihr Zwischenverzeichnis absichtlich im
**Zielordner** an. Ist der gerade nicht beschreibbar, weicht das Programm aus
– und trug den Ausweichort danach als neuen **Arbeitsordner** in die
Einstellungen ein. Damit war die eigene Angabe überschrieben, durch einen
Vorgang, der mit ihr nichts zu tun hatte.

Die Folge trifft erst später und woanders: Fällt der Ausweich auf das
Systemlaufwerk, arbeitet ab da jede Aufgabe dort. Auf dem Prüfrechner sind
das 40 GB frei gegen 3454 GB auf dem eingestellten Laufwerk – ein großer
Titel scheitert dann an vollem Datenträger.

## Kleineres

* Der Weg **Dump-Ordner → .ffpfsc** meldete „Schritt 1 / 2 … inneres PFS …
  Nested-PFS-Pipeline", obwohl er in der Vorgabe-Bauform einen **einzigen**
  Durchgang macht. Der Kommentar im Quelltext sagte es zwei Zeilen weiter
  sogar selbst („Ein Schritt statt zwei").
* Dreizehn Meldungen der Abschlussphase standen fest auf Deutsch – in der
  englischen Oberfläche erschien dort „Validierung…", „Abschluss…",
  „Metadaten aufbereiten…". v1.9.7 hatte die beiden anderen Phasen
  umgestellt und diese übersehen; die Prüfung dazu kannte nur zwei der drei
  Phasen und deckte die Lücke mit. Sie prüft jetzt alle drei und zusätzlich
  jeden Aufruf.

## Was daran gemessen ist

Vier neue Wächter, jeder gegengeprobt: Fehler wieder einbauen, Prüfung fällt,
zurücksetzen, grün. Dazu echte Läufe an echten Titeln:

| Aufgabe | Titel | Ergebnis |
| --- | --- | --- |
| 1 → `.exFAT` | Matchbox Driving Adventures (5,6 GB) | 6,04 GB |
| 1 → `.ffpfsc` | Crash Bandicoot 4 (47,8 GB) | 23,3 GB |
| 1 + Backport FW 7 + AMPR EMU + Asset-Pack | Matchbox | 5,22 GB, Prüfung Byte für Byte bestanden |
| 2 → Dump-Ordner | Matchbox (mit Asset-Pack) | 211 Dateien, 9,53 GB |
| 3 `.exFAT` → `.ffpfsc` | Matchbox | 3,01 GB |
| 8 Validator | Matchbox | bestanden |
