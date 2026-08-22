# PS5 Dump & Image Converter v1.8.83

**22.08.2026**

Zwei neue Knöpfe im Hauptfenster: **AMPR EMU – alte Methode** und
**AMPR EMU – neue Methode**.

## Warum zwei

Zwischen ShadowMountPlus **1.7 alpha6** und **1.7 alpha8** wurde umgebaut, wo
das Werkzeug nach den Ersatzbibliotheken sucht. Das ist die teuerste Sorte
Änderung: Eine Ablage, die vorher richtig war, wirkt danach nicht mehr — und
zwar lautlos. Keine Meldung, kein Eintrag im Protokoll; das Spiel startet
einfach ohne seine Bibliotheken.

| | alte Methode (bis alpha6) | neue Methode (ab alpha8) |
| --- | --- | --- |
| Wo gesucht wird | `app0/fakelib2`, sonst `app0/fakelib` — aus der laufenden Sandbox | feste Reihenfolge: `backports/<ID>/fakelib2` → `backports/<ID>/fakelib` → `<Spiel>/fakelib` |
| `fakelib2` im Spielordner | wirkt | **wird ignoriert** |
| global + spieleigen | zwei unionfs-Schichten | vorher zusammenkopiert nach `/data/shadowmount/cache/<ID>/fakelib/` |
| Emulator-Dateien | gibt es nicht | aus `/data/shadowmount/emus/`, ersetzt nur Vorhandenes |
| `config.ini`-Schlüssel | 5 | 9 |

**Welchen Knopf man braucht, muss man nicht wissen.** Beide stellen beim Start
fest, welche Fassung auf der Konsole läuft, und sagen es. Beim falschen kommt
eine Rückfrage mit Begründung und dem Rat, den anderen zu nehmen.

## Die Knöpfe erledigen alles selbst

Kein Formular — der Knopf fängt an zu arbeiten. Sechs Schritte, die im Fenster
mitlaufen:

```text
[1/6] PS5 im Netz finden
[2/6] Welche ShadowMount+-Fassung läuft dort?     mit Belegen
[3/6] Spiele suchen                               auch aus eingehängten Abbildern
[4/6] Ablageort bestimmen                         die Fassung entscheidet
[5/6] Neueste libSceAmpr.sprx auswählen
[6/6] config.ini abgleichen, ablegen, zurücklesen
```

### Die PS5 wird gesucht, nicht vorausgesetzt

Erst die Adresse aus den Einstellungen — steht dort etwas, muss es auch
antworten. Dann die gespeicherten FTP-Profile. Sonst das eigene Netz: 254
Adressen mit 64 Fäden, rund vier Sekunden je Netz.

Ein offener Port genügt dabei nicht. Jeder Treffer muss ein Verzeichnis öffnen
können, das es nur auf einer PS5 gibt (`/system_data`, `/mnt/sandbox`,
`/user`) — sonst hielte ein Drucker im Netz die Suche für erfolgreich.

Gesucht wird außerdem in **allen** plausiblen Netzen, nicht nur im
erstbesten: Auf einem Rechner mit WSL oder Hyper-V nennt das System zuerst den
virtuellen Adapter. Beim Nachmessen war das `172.25.128.x`, während die Konsole
in `192.168.1.x` stand. Die Netze der gespeicherten FTP-Profile zählen deshalb
mit — dort stand die Konsole schon einmal.

### Gefragt wird nur, wo es etwas zu entscheiden gibt

Und dann nicht mit „Ja/Nein". Der Dialog zeigt die Frage, einen Absatz *warum*
gefragt wird, und unter **jeder** Antwortmöglichkeit einen Satz, was sie
bedeutet. Die empfohlene steht vorn und ist gekennzeichnet.

Fünf Fragen können vorkommen:

* welche Konsole, wenn mehrere antworten
* ob die gefundene Adresse gespeichert werden soll
* welches Spiel, wenn mehrere da sind
* ob `libScePlayGo.sprx` mit dazu soll — mit der Erklärung, wann man es braucht
* ob abweichende Schlüssel in der `config.ini` angepasst werden sollen

Ein Abbruch steigt an jeder Stelle sofort aus, ohne etwas zu verändern.

## An der echten Konsole gemessen

Der Lauf wurde an einer PS5 mit Firmware 12.00 und ShadowMountPlus 1.7 alpha6
durchgeführt:

```text
Adresse in den Einstellungen : leer
FTP-Profil                   : 192.168.1.96 (tot, von Juni)
→ gefunden: 192.168.1.94 in 4,7 s

Fassung erkannt : alt — passt zum gedrückten Knopf
Spiele gefunden : 9
Bibliothek      : libSceAmpr.sprx 0.3.6.4 (no debug)
config.ini      : 0 Abweichungen
abgelegt        : /data/homebrew/backports/CUSA03877/fakelib2/
```

Die abgelegte Datei wurde zurückgelesen: 236 278 Bytes, byteweise identisch
mit der Quelle. Genau zwei Fragen wurden gestellt.

**Drei Fehler kamen dabei ans Licht**, die am Schreibtisch unsichtbar waren:

1. Die Spielsuche fand **null** Spiele, weil sie nach entpackten Ordnern mit
   `eboot.bin` suchte. Die Spiele laufen aber aus eingehängten Abbildern — da
   gibt es keinen solchen Ordner. Zusätzliche Quelle ist jetzt
   `/system_data/priv/appmeta/`: **9 statt 0**.
2. Die `config.ini`-Prüfung meldete vier Abweichungen. Die Datei auf der
   Konsole besteht aber aus 146 Zeilen, die **alle Kommentar** sind — kein
   Schlüssel gesetzt, ShadowMount+ läuft auf seinen Vorgaben, und die sind
   richtig. Jetzt zählt nur, was gesetzt ist und abweicht.
3. Die Adresssuche lief im WSL-Netz statt im LAN (siehe oben).

## Tests

Zwei neue Dateien mit zusammen **70 Tests**: `test_shadowmount_generation.py`
für die Ablageregeln beider Fassungen, `test_ampr_generation.py` für die
Automatik, die Adresssuche und die erklärten Fragen. Letztere halten
strukturell fest, dass es zu jeder Frage eine Begründung und zu jeder
Antwortmöglichkeit eine eigene Erklärung gibt. **1189 Tests laufen durch.**

Die Regeln selbst stehen in `ps5_validator/utils/shadowmount_generation.py` —
getrennt von der Oberfläche, damit sie prüfbar bleiben.

## Handbuch

Abschnitt 13.8 ist neu und stellt die beiden Methoden gegenüber, erklärt die
sechs Schritte und die fünf möglichen Fragen.
