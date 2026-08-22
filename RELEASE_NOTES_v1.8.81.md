# PS5 Dump & Image Converter v1.8.81

**22.08.2026**

Diese Ausgabe nimmt etwas zurück. Der Knopf **NP-BINDUNG** aus v1.8.80 ist
wieder ausgebaut, und mit ihm alle Aussagen, die auf ihm aufbauten.

## Warum

v1.8.80 versprach, die Trophäen für Spiele aus einem Abbild wieder zum Laufen
zu bringen. Das war falsch. Der Knopf legte die `npbind.dat` zwar an genau die
Stelle, an die sie gehört — aber es ändert nichts. Die Trophäen registrieren
sich weder mit ihr noch ohne sie.

Der Irrtum entstand aus **einem einzigen** Spielstart, der ohne Fehlermeldung
durchlief. Er war untypisch. Später zeigte derselbe Aufbau den Fehler wieder,
und ein direkter Blick ins Dateisystem der Konsole entschied die Frage
endgültig: Unter `/user/trophy/conf/` legt jeder registrierte PS4-Titel einen
Ordner an. Für die Titel aus dem Abbild stand dort nie einer — mit Datei wie
ohne.

## Was wirklich dahintersteckt

`0x80551618` kommt aus Sonys NPDRM-Prüfkette. Sie verlangt ein **regulär
installiertes Paket**, und ein eingehängtes Abbild ist keines. Am Abbild, an
der Konvertierung und an ShadowMount+ liegt es nicht — es ist so vorgesehen
und mit Bordmitteln nicht zu ändern.

Nachgemessen wurde das an zwei Titeln mit insgesamt neun Starts aus dem Abbild
und zwei Starts nach Installation über den Package Installer:

| Lauf | Trophäen registriert |
| --- | --- |
| über den Package Installer installiert | **ja**, sofort beim ersten Start |
| aus dem Abbild, ohne `npbind.dat` | nein |
| aus dem Abbild, mit `npbind.dat` in `appmeta/` | nein |
| aus dem Abbild, zusätzlich mit `param.sfo` | nein |
| aus dem Abbild, `npbind.dat` in `appmeta/…/trophy2/` | nein |

### Der Gegenbeweis: PS5-Titel sind nicht betroffen

Das Wichtigste an der ganzen Suche, weil es eine ganze Klasse von Ursachen
ausschließt. Für **jeden** Titel der Konsole wurde die NPWR-Kennung aus seiner
`npbind.dat` gelesen und gegen die tatsächlichen Registrierungen gehalten:

| Titel | Herkunft | System | registriert |
| --- | --- | --- | --- |
| CUSA00775 | Package Installer | PS4 | **ja** |
| CUSA03877 | Abbild | PS4 | nein |
| PPSA02433, PPSA03117, PPSA07029 | Abbild | PS5 | **ja** |
| PPSA15246, PPSA16709, PPSA25872 | Abbild | PS5 | **ja** |

**Sechs von sechs PS5-Titeln laufen aus Abbildern und registrieren ihre
Trophäen.** Es liegt also nicht am Abbildbetrieb und nicht an ShadowMount+.
PS5-Titel gehen über die neuere Trophäenkette, PS4-Titel über Sonys alte — und
nur die verlangt ein installiertes Paket.

Auch der komplette Registrierungseintrag von Hand nachgebaut
(`/user/trophy/conf/<NPWR>/` mit `TROPHY.TRP` aus dem Abbild und passender
`TRPPARAM.INI`) ändert nichts: Der Ordner lag nach dem Spielstart
**unverändert** da — das System hatte ihn nicht einmal angesehen. Die Sperre
sitzt im Programmcode der Konsole, nicht in fehlenden Dateien.

**Wer die Trophäen braucht, installiert über den Package Installer.** Der
Abbildweg bleibt für alles andere — er spart den Speicherplatz der
Installation.

## Was sich im Programm ändert

* Der Knopf **NP-BINDUNG** ist weg. Die Knopfreihe im PS4-Fenster hat wieder
  ihre vier Schaltflächen.
* Die elf Meldungen dazu und die beiden Methoden dahinter sind entfernt.
* Der Hinweis nach dem Bauen bleibt — aber er sagt jetzt, was gemessen ist:
  dass Trophäen im Abbildbetrieb nicht registrieren, warum das so ist, und
  dass Nachlegen von Dateien nichts daran ändert.

## Nebenbei: der Kommandozeilenmodus meldete stillen Erfolg

Beim Durchtesten aufgefallen. Ein Aufruf wie

```
--cli --task 3 --source "…exfat" --dest "…" --format ffpfsc --yes
```

beendete sich unter Windows ohne Administratorrechte mit **Exit-Code 0**, ohne
irgendetwas getan zu haben. Das Programm ruft an dieser Stelle
`ShellExecuteW("runas")` auf, um sich mit erhöhten Rechten neu zu starten — der
neue Prozess läuft aber abgekoppelt, und weder seine Ausgabe noch sein
Exit-Code erreichen den Aufrufer. Für den GUI-Modus ist das richtig, für einen
Skriptlauf nicht: Er meldete Erfolg, wo nichts geschehen war.

`--cli` bricht in diesem Fall jetzt mit **Exit-Code 3** ab und nennt den Grund.
Die Meldung geht durch `_prepare_cli_streams()`, damit die Umlaute auch dann
stehen bleiben, wenn die Ausgabe in eine Datei umgeleitet wird. Vier Tests in
`test_cli_logging.py` halten die Stelle fest.

## Die EXE meldete neun Ausgaben lang die falsche Version

Beim Bauen aufgefallen. In den Dateieigenschaften der fertigen EXE stand
**1.8.72.0** — die Nummer aus `file_version_info.txt`, die seit v1.8.72 nicht
mehr mitgezogen worden war. Sichtbar wird sie nur, wenn man die Eigenschaften
im Explorer aufschlägt; im Programm selbst stand immer die richtige.

Die Versionsnummer steht an vier Stellen: `APP_VERSION` im Hauptprogramm, im
Zielnamen der `.spec`, in `file_version_info.txt` und in `Build_EXE.ps1`. Die
ersten beiden wurden schon gegeneinander geprüft, die anderen beiden nicht.

Alle vier stehen jetzt auf v1.8.81, und **vier neue Tests halten sie
zusammen**. Sie stehen in `test_build_ready.py` — einer Datei, die bisher ein
reines Handskript ohne Testklasse war und unter `unittest discover` null Tests
beitrug. Genau deshalb ist der Drift jahrelang niemandem aufgefallen.

## Handbuch

Abschnitt 13.8 ist neu geschrieben. Der Kasten zur NP-Bindung und der
Abschnitt zum Knopf sind ersetzt durch zwei Kästen: einen zur
Trophäengrenze mit der belegten Ursache und dem Hinweis auf
`/user/trophy/conf/`, und einen zum Ladebildschirm-Hänger, der ehrlich sagt,
dass die Ursache offen ist und was alles ausgeschlossen wurde.

## Tests

`NpBindungTests` ist entfallen. An seine Stelle treten zwei Tests, die
festhalten, dass die widerlegte Behauptung draußen bleibt und der belegte Text
an ihrer Stelle steht. 1173 Tests laufen durch.
