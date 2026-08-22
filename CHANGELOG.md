# Changelog – PS5 Dump & Image Converter

Dieser Changelog beschreibt in einfacher Sprache, was sich in den einzelnen Versionen für dich als Nutzer verändert hat. Neuste Version steht oben. Rein technische Änderungen (z. B. am Bauprozess oder an internen Tests) sind hier bewusst weggelassen.

> **Kurz zum aktuellen Stand (v1.8.85):** **PS4 PKG → ffpfsc** ist wieder da – vollständig, wie vor dem Ausbau in v1.8.82. Ohne den Knopf NP-BINDUNG, der schon vorher raus war.

---

## v1.8.85 – 23.08.2026

### PS4 PKG → ffpfsc ist wieder da

Die Funktion war in v1.8.82 vollständig entfernt worden. Sie ist jetzt
vollständig zurück:

| | |
| --- | --- |
| Eingebettetes Werkzeug | `PS4FFPFSC-0.2.8/` – 52 Dateien, 11 MB |
| Fenster und Menüeintrag | wie vorher, unter **WEITERE TOOLS** |
| Texte | 65 Sprachschlüssel |
| Tests | 71 Prüfungen in zwei Dateien, dazu der Layouttest |
| Handbuch | der Abschnitt – jetzt als **13.9**, weil 13.8 inzwischen AMPR EMU ist |

### Was NICHT zurückkommt

**Der Knopf NP-BINDUNG.** Der war schon eine Ausgabe vor dem Ausbau entfernt
worden, in v1.8.81, nachdem an der Konsole gemessen war, dass er nichts
bewirkt: Trophäen registrieren sich bei PS4-Titeln aus einem Abbild nicht,
und daran ändert das Nachlegen von Dateien nichts. Wiederhergestellt wurde
deshalb der Stand von **v1.8.81** – die Funktion vollständig, aber ohne dieses
Versprechen.

Aus demselben Grund trägt der Handbuchabschnitt den **korrigierten** Text: die
belegte Ursache, den Gegenbeweis über sechs PS5-Titel und alle vier
widerlegten Versuche – nicht die überholte Fassung von v1.8.80.


## v1.8.84 – 23.08.2026

### Werkzeugfenster bleiben vorn

Hattest du ein Fenster aus der oberen Leiste offen und wolltest den nächsten
Knopf drücken, war das erste danach verschwunden. Es lag hinter dem
Hauptfenster.

Schuld war nicht das Öffnen des zweiten Fensters, sondern der Klick auf das
Hauptfenster, den du brauchst, um an den Knopf zu kommen: Der holt es nach
vorn, und die Werkzeugfenster gehörten bisher zu niemandem – Windows hatte
also keinen Anlass, sie oben zu halten.

Jetzt gehören sie zum Hauptfenster und bleiben garantiert davor. **Ihren
Eintrag in der Taskleiste behalten sie**, und über Alt+Tab sind sie weiterhin
erreichbar.

Mitgenommen wurden dabei drei Fenster, die an der gemeinsamen Fensterroutine
vorbei entstehen – darunter **CREDITS**.

**Eine Änderung, die du merken wirst:** Weil die Fenster jetzt zum
Hauptfenster gehören, wandern sie mit ihm in die Taskleiste, wenn du es
minimierst – und kommen beim Wiederherstellen zurück.


## v1.8.83 – 22.08.2026

### Zwei neue Knöpfe: AMPR EMU, alte und neue Methode

Zwischen ShadowMountPlus **1.7 alpha6** und **1.7 alpha8** hat sich geändert,
wo das Werkzeug nach den Ersatzbibliotheken sucht. Der Haken: Eine Ablage, die
vorher richtig war, wirkt danach **nicht mehr** – ohne Fehlermeldung. Das Spiel
startet einfach ohne sie.

| | alte Methode | neue Methode |
| --- | --- | --- |
| Wo gesucht wird | `app0/fakelib2`, sonst `app0/fakelib` | `backports/<ID>/fakelib2` → `backports/<ID>/fakelib` → `<Spiel>/fakelib` |
| `fakelib2` im Spielordner | wirkt | **wird ignoriert** |
| global + spieleigen | zwei Schichten | vorher zusammenkopiert in einen Cache |
| Emulator-Dateien | gibt es nicht | aus `/data/shadowmount/emus/` |

**Welchen Knopf du brauchst, musst du nicht wissen.** Beide prüfen beim Start,
welche Fassung auf deiner Konsole läuft, und sagen es dir. Hast du den falschen
erwischt, kommt eine Rückfrage mit Begründung.

### Die Knöpfe erledigen alles selbst

Kein Formular zum Ausfüllen – der Knopf fängt an zu arbeiten. Er sucht die PS5
im Netz, stellt die ShadowMount+-Fassung fest, findet die Spiele (auch die aus
eingehängten Abbildern), bestimmt den Ablageort, nimmt die neueste
`libSceAmpr.sprx` und gleicht die `config.ini` ab. Zum Schluss wird die
abgelegte Datei zurückgelesen und geprüft.

**Die PS5 findet er selbst.** Erst die Adresse aus den Einstellungen, dann die
gespeicherten FTP-Profile, sonst das eigene Netz – rund vier Sekunden. Ein
offener Port genügt dabei nicht: Es muss sich ein Verzeichnis öffnen lassen,
das es nur auf einer Konsole gibt. Wird eine gefunden, die noch nicht
gespeichert ist, fragt er, ob er sie merken soll.

### Gefragt wird nur, wo es etwas zu entscheiden gibt

Und dann nicht mit „Ja/Nein". Unter jeder Antwortmöglichkeit steht ein Satz,
was sie bedeutet, und die empfohlene ist gekennzeichnet. Fünf Fragen können
vorkommen: welche Konsole, ob die Adresse gespeichert werden soll, welches
Spiel, ob `libScePlayGo.sprx` mit dazu soll, und ob abweichende Schlüssel in
der `config.ini` angepasst werden sollen. Ein Abbruch steigt überall sofort
aus, ohne etwas zu verändern.


## v1.8.82 – 22.08.2026

> **Überholt.** In v1.8.85 ist die Funktion wieder eingebaut. Das Folgende bleibt als Verlauf stehen.

### Die Funktion PS4 PKG → ffpfsc ist entfernt

Das Fenster, das aus PS4-PKG-Dateien Abbilder baute, gibt es nicht mehr. Mit
ihm verschwinden das eingebettete Werkzeug **PS4FFPFSC 0.2.8** (12 MB,
77 Dateien), 1 141 Zeilen Programmcode, 65 Texte, der Eintrag in der
Titelleiste und Abschnitt 13.8 des Handbuchs.

**Die EXE schrumpft von 116,3 MB auf 112,1 MB** – 4,2 MB weniger. Nicht die
vollen 12 MB: PyInstaller komprimiert die Datenordner im Bündel.

### Was bleibt

Alles andere. PS5-Abbilder werden weiterhin in allen bisherigen Aufgaben
umgewandelt: Dump-Ordner, `.ffpfsc`, `.exfat`, `.ffpkg`, Sammelkonvertierung,
AIO, AMPR EMU Manager und Validator. Die MkPFS-Packmaschine bleibt ebenfalls –
sie hat mit dem PS4-Werkzeug nichts zu tun.

Wer aus PS4-PKG-Dateien Abbilder bauen will, braucht dafür künftig ein anderes
Werkzeug. Was bei der Arbeit daran herausgekommen ist, bleibt in den Einträgen
zu v1.8.79 bis v1.8.81 stehen – vor allem, dass ein PS4-Titel aus einem Abbild
keine Trophäen registriert und dass Abbilder in die Wurzel des Datenträgers
gehören.


## v1.8.81 – 22.08.2026

### Zurückgenommen: der Knopf NP-BINDUNG

Der Knopf aus v1.8.80 ist wieder ausgebaut. Er hat die Trophäen **nicht**
repariert – das Versprechen war falsch.

Es entstand aus **einem einzigen** Spielstart, der ohne Fehlermeldung
durchlief. Der Lauf war untypisch. Später zeigte derselbe Aufbau den Fehler
wieder, und ein Blick ins Dateisystem der Konsole entschied es endgültig:
Unter `/user/trophy/conf/` legt jeder registrierte PS4-Titel einen Ordner an –
für die Titel aus dem Abbild stand dort nie einer, mit Datei wie ohne.

### Was wirklich dahintersteckt

`0x80551618` kommt aus Sonys Prüfkette, und die verlangt ein **regulär
installiertes Paket**. Ein eingehängtes Abbild ist keines. Am Abbild, an der
Konvertierung und an ShadowMount+ liegt es nicht – es ist so vorgesehen.

An zwei Titeln nachgemessen, mit neun Starts aus dem Abbild und zwei nach
Installation über den Package Installer:

| Lauf | Trophäen registriert |
| --- | --- |
| über den Package Installer installiert | **ja**, sofort beim ersten Start |
| aus dem Abbild, ohne `npbind.dat` | nein |
| aus dem Abbild, mit `npbind.dat` in `appmeta/` | nein |
| aus dem Abbild, zusätzlich mit `param.sfo` | nein |
| aus dem Abbild, `npbind.dat` in `appmeta/…/trophy2/` | nein |

### PS5-Titel sind davon nicht betroffen

Für jeden Titel der Konsole geprüft, ob seine Trophäen registriert sind:
**Sechs PS5-Titel liefen aus Abbildern und hatten alle sechs registriert** –
nur der PS4-Titel nicht. Am Abbildbetrieb liegt es also nicht. PS5-Spiele
gehen über die neuere Trophäenkette, PS4-Spiele über Sonys alte, und nur die
verlangt die Installation.

Auch der Registrierungseintrag von Hand nachgebaut ändert nichts – er lag nach
dem Spielstart unverändert da, das System hatte ihn nicht einmal angesehen.


**Brauchst du die Trophäen, installiere über den Package Installer.** Für
alles andere bleibt der Abbildweg – er spart den Speicherplatz der
Installation.

### Die EXE zeigt wieder ihre richtige Version an

In den Dateieigenschaften der EXE stand **1.8.72.0** – die Nummer war seit
v1.8.72 nicht mehr mitgezogen worden. Im Programm selbst stand immer die
richtige; sichtbar war der Fehler nur im Explorer unter „Eigenschaften".

Jetzt stehen alle vier Stellen, an denen die Version vorkommt, auf demselben
Stand, und vier neue Tests halten sie künftig zusammen.


### Der Kommandozeilenmodus meldet keinen stillen Erfolg mehr

Beim Testen aufgefallen: Ein Aufruf mit `--cli` beendete sich unter Windows
ohne Administratorrechte mit **Exit-Code 0** – ohne irgendetwas getan zu haben.
Das Programm versucht dort, sich mit erhöhten Rechten neu zu starten; der neue
Prozess ist aber abgekoppelt, und weder seine Ausgabe noch sein Exit-Code
kommen beim Aufrufer an. Ein Skript hielt die Aufgabe für erledigt.

Jetzt bricht `--cli` in diesem Fall mit **Exit-Code 3** ab und sagt, was zu tun
ist: Eingabeaufforderung oder PowerShell als Administrator öffnen. Im
GUI-Modus bleibt alles wie gehabt – dort ist der Neustart mit UAC-Dialog genau
richtig.


### Der Hinweis nach dem Bauen bleibt, sagt aber die Wahrheit

Erkennt das Programm einen PS4-Titel, steht im Protokoll weiterhin ein
Hinweis. Neu ist, was darin steht: dass Trophäen im Abbildbetrieb nicht
registrieren, warum das so ist, und dass Nachlegen von Dateien nichts daran
ändert. Im Handbuch ist Abschnitt 13.8 entsprechend neu geschrieben – dazu ein
zweiter Kasten für Spiele, die im Ladebildschirm hängen bleiben, der offen
sagt, dass die Ursache dort ungeklärt ist.


## v1.8.80 – 22.08.2026

> **Überholt.** Der hier beschriebene Knopf ist in v1.8.81 wieder ausgebaut worden – er hat die Trophäen nicht repariert. Das Folgende bleibt als Verlauf stehen.

### Der Knopf NP-BINDUNG

In v1.8.79 stand nur, **warum** die Trophäen scheitern. Jetzt lässt es sich beheben.

Unten links im PS4-Fenster gibt es den Knopf **NP-BINDUNG**. Er holt die `sce_sys/npbind.dat` aus dem fertigen Abbild und legt sie über FTP nach `/system_data/priv/appmeta/<Title-ID>/` – genau dorthin, wo die Konsole sie sucht und wo ShadowMount+ sie nicht ablegt.

**Wann du ihn drückst:** erst, wenn das Spiel auf der PS5 schon erscheint. Der Zielordner entsteht nämlich erst mit der Registrierung. Also: Abbild erstellen, auf den Datenträger legen, warten bis es eingelesen ist – und dann zurück ins Fenster, Spiel markieren, Knopf drücken. Ist der Titel noch nicht registriert, sagt dir das Protokoll genau das.

**Was er nicht tut:** Eine vorhandene Bindung wird nie überschrieben. Hast du das Spiel regulär über den Package Installer installiert, hat dessen Bindung Vorrang. Nach dem Ablegen wird die Datei zurückgelesen und verglichen.

Nachgemessen: Die `npbind.dat` aus unserem Abbild ist **byteweise identisch** mit der, die der Package Installer ablegt – es wird also nichts Erfundenes hingelegt, sondern genau die Datei, die dazugehört.

**Voraussetzung:** Die Adresse deiner PS5 muss in den Einstellungen stehen und die Konsole per FTP erreichbar sein – dieselbe Verbindung, die auch der AMPR EMU Manager nutzt.

## v1.8.79 – 22.08.2026

### PS5-Pakete werden benannt statt verschwiegen

Legst du einen Ordner mit PS5-Paketen ins PS4-Fenster, stand dort bisher nur **„0 Spiel(e) gefunden"** – ohne einen Grund. Jetzt sieht das Programm in die ersten vier Bytes jeder Datei und sagt dir, was los ist:

> In der Quelle liegen 4 Paket(e) für die PS5. Dieses Fenster baut Abbilder aus PS4-Paketen; PS5-Pakete kann das eingebettete Werkzeug nicht öffnen. Sie bleiben unberücksichtigt: …

Das kostet nichts – vier Bytes am Dateianfang, kein Entpacken. `\x7FCNT` ist ein PS4-Paket, `\x7FFIH` ein PS5-Paket. An 31 Paketen nachgemessen (20 PS4, 11 PS5): Das Kennzeichen stimmte ausnahmslos mit der Title-ID im Paket überein.

### Der Ablageort-Hinweis kommt zweimal statt viermal

Er erscheint jetzt **einmal eine Minute nach dem Start** und **einmal bei der Hälfte**. Die erste hängt bewusst an der Uhr und nicht am Fortschritt: Am Anfang steht der Balken je nach Spielgröße unterschiedlich lange bei wenigen Prozent – „eine Minute nach dem Start" ist dagegen bei jedem Spiel dieselbe Stelle. Dauer und Aussehen bleiben: 25 Sekunden, langsam ein- und ausgeblendet, kein Klick nötig.

### Richtigstellung: Eigene Ordner auf dem Stick

In v1.8.77 stand, ein selbst angelegter Ordner wie `/mnt/usb0/ps4ffpsc/` werde „nicht gefunden". Das war zu absolut. Richtig ist: Die **automatische Suche** geht dort nicht hinein – aber mit einem Eintrag in `/data/shadowmount/manual.lst` funktioniert er, das Spiel startet von dort.

Nur ist das nicht neustartfest. Der Eintrag hält einen absoluten Pfad samt Einhängepunkt fest, und hängen mehrere USB-Geräte an der Konsole, kann sich die Nummer beim Neustart drehen – aus `usb0` wird `usb1`, und der Titel ist weg. **Deshalb weiterhin: Abbild direkt in die Wurzel des Datenträgers.** Nicht weil ein Unterordner unmöglich wäre, sondern weil die Anheftung daran zerbricht.

### Neu dokumentiert: warum Trophäen scheitern

> **Überholt.** Die hier genannte Ursache stimmt nicht. Die Trophäen scheitern an Sonys Prüfkette, nicht an der NP-Bindung – siehe v1.8.81.

Startet ein PS4-Spiel aus einem Abbild, meldet die Konsole jedes Mal `Trophy registration failed (0x80551618)`. Der Grund liegt nicht am Abbild: ShadowMount+ sucht die NP-Bindung nur an den PS5-Stellen `sce_sys/trophy2/` und `sce_sys/uds/`. Ein PS4-Spiel legt sie flach unter `sce_sys/npbind.dat` ab – die Datei **ist im Abbild enthalten**, sie wird nur nie abgeholt.

Das Programm sagt das jetzt nach jedem Bau, und im Handbuch steht der ganze Zusammenhang. Denn ohne diese Erklärung sieht es aus wie ein Fehler der Konvertierung – und ist keiner.

## v1.8.78 – 22.08.2026



### Das PS4-Fenster sagt jetzt, für welche Konsole ein Titel ist



In der Liste der gefundenen Spiele steht eine neue Spalte **Konsole**. Sie sagt „PS4“ oder „PS5“, und zwar sofort beim Einlesen – nicht erst, wenn das Abbild fertig gebaut ist.



Das ist mehr als eine Auskunft: Dieses Fenster baut Abbilder aus **PS4**-Paketen. Legst du versehentlich ein PS5-Spiel hinein, wird die Zeile farbig hervorgehoben und im Protokoll steht, dass du dafür die Aufgaben 1 bis 6 nehmen sollst. Bisher hättest du den ganzen Bau abgewartet, um das zu erfahren.



Erkannt wird an der Title-ID: `CUSA` und `PUSA` sind PS4, `PPSA`, `PPSS`, `PPUS` und `PPJP` sind PS5. Sagt die Kennung nichts – etwa bei einem PS3-Titel mit `NPUB` –, steht dort **unklar** statt einer Vermutung.



### Die Nachprüfung des Abbilds hat nie stattgefunden



Nach jedem Bau meldete das Protokoll, das fertige Abbild werde geprüft, und gleich danach: `Das Abbild ließ sich nicht nachprüfen: [Errno 13] Permission denied`. Der Grund war eine vertauschte Übergabe – die Prüfung bekam den Zielordner statt der erzeugten Datei. Sie ist also seit ihrer Einführung nie gelaufen, obwohl sie genau dafür da ist, dir zu sagen, was wirklich im Abbild steht.



Aufgefallen ist das bei einer echten Konvertierung. Jetzt sucht das Programm die gebaute Datei im Zielordner – bevorzugt die zur Title-ID und zum gewählten Format – und prüft sie. Am Testtitel meldet sie sauber **113 Dateien**.



### Die Einblendung geht nicht mehr nach dem Ende auf



Der Hinweis zum Ablageort erschien in seltenen Fällen noch, wenn die Umwandlung schon fertig war – der letzte Sprung des Fortschrittsbalkens auf 100 % löste ihn nachträglich aus. Nach dem Ende kommt keine Einblendung mehr.



## v1.8.77 – 21.08.2026

### Ein dritter Ort, der funktioniert

`/mnt/usb0/etaHEN/games` wurde nachgemessen und tut es: Die Datei versuchsweise dorthin verschoben, binnen 20 Sekunden von ShadowMount+ eingehängt, danach zurückgelegt. Damit sind drei Orte auf dem Stick belegt:

| Ort | gemessen |
| --- | --- |
| `/mnt/usb0/` | binnen 15 Sekunden gefunden |
| `/mnt/usb0/homebrew/` | binnen 20 Sekunden eingehängt |
| `/mnt/usb0/etaHEN/games` | binnen 20 Sekunden eingehängt |

Ein selbst angelegter Ordner wie `/mnt/usb0/ps4ffpsc/` wird weiterhin nicht gefunden, und der interne Speicher bleibt tabu.

### Das PS4-Fenster ist wieder aufgeräumt

Der Ablageort-Kasten und die Hinweiszeile darunter standen dauerhaft im Fenster, obwohl man sie nur einmal lesen muss. Beides ist jetzt ausschließlich in der Einblendung, die während der Umwandlung erscheint – dort erreicht der Hinweis dich im richtigen Moment, nämlich während du auf den Balken wartest.

Das Fenster braucht dadurch **769 statt 959 Pixel** Höhe. Zum Vergleich: In v1.8.74 war es einen einzigen Pixel vom Überlaufen entfernt.

### Die Einblendung bleibt 25 Sekunden

Weil sie jetzt den ganzen Text trägt – Überschrift, die drei Zeilen, die Belege und die Einschränkung des Werkzeugs – wären 15 Sekunden zu knapp zum Lesen. Alles andere bleibt: viermal über den Vorgang verteilt, langsam ein- und ausgeblendet, ohne dass du etwas drücken musst.

## v1.8.76 – 21.08.2026

### Der wichtigste Hinweis kommt jetzt von selbst

Während eine PS4-Konvertierung läuft und du auf den Balken schaust, blendet sich der Hinweis ein, worauf es beim fertigen Abbild ankommt: **Es darf nur vom externen USB-Datenträger starten, nie von der internen SSD** – sonst reißt es beim Start die Konsole mit sich.

Die Einblendung erscheint **viermal** über den ganzen Vorgang verteilt, bleibt **15 Sekunden** stehen und blendet sich langsam ein und wieder aus. Du musst nichts drücken; sie geht von allein.

Verteilt wird nach Fortschritt, nicht nach Uhrzeit: Ein kleines Spiel ist in zwei Minuten fertig, ein großes braucht eine Stunde – so liegt sie in beiden Fällen richtig.

### Richtigstellung: /mnt/usb0/homebrew/ funktioniert doch

In v1.8.74 stand im PS4-Fenster „Unterordner werden nicht durchsucht". Das war zu pauschal und hätte dich von einem Ordner abhalten können, der funktioniert.

Nachgemessen an der Konsole: Ein Abbild in `/mnt/usb0/` wird binnen 15 Sekunden gefunden, eines in `/mnt/usb0/homebrew/` binnen 20 – eines in einem selbst angelegten Ordner nie. ShadowMount+ durchsucht nicht „keine Unterordner", sondern **nur die Pfade seiner eingebauten Liste**. `homebrew` steht darauf, ein eigener Ordner nicht.

### Der Kasten sagt es jetzt in drei Zeilen

Vorher brauchte er sieben und drückte das Fenster an den Rand des Bildschirms. Jetzt steht dort das Nötige, die Einzelheiten stehen im Tooltip:

```text
NUR VOM USB-DATENTRÄGER STARTEN
✓  Auf den USB-Datenträger: /mnt/usb0/ oder /mnt/usb0/homebrew/
✗  Nie auf die interne SSD – /data/homebrew und /data/etaHEN/games geben einen Kernel Panic
!  Eigene Ordner wie /mnt/usb0/ps4ffpsc/ werden nie gefunden
```

Das Fenster braucht dadurch 959 statt 1012 Pixel Höhe – vorher war es einen Pixel vom Überlaufen entfernt.

## v1.8.75 – 21.08.2026

### Am Programm ändert sich nichts

Diese Ausgabe fasst ausschließlich die Testreihe an. Wer v1.8.74 benutzt, verpasst keine Funktion und keine Fehlerbehebung – die Bauten verhalten sich identisch. Sie ist trotzdem eigenständig, weil das mitgelieferte Prüfsummen-Verzeichnis jetzt den kompletten Testbestand mitführt.

### Der Testbestand liegt jetzt offen

Bisher blieben die Testdateien lokal; nur sieben von 58 lagen im Repository, und das eher aus Versehen. Wer nachvollziehen wollte, womit eine Aussage in diesem Changelog belegt ist, fand die Prüfungen nicht. Jetzt sind alle 58 dabei – zusammen rund 860 KB Text.

### Drei Ursachen für unzuverlässige Testläufe behoben

Ein Test schlug in einem Gesamtlauf fehl und lief in vier weiteren durch. Dahinter steckten drei voneinander unabhängige Dinge, keines davon eine Eigenheit, mit der man leben muss:

**Eine zerstörte Fensterwurzel.** Eine Prüfung „ist überhaupt eine Anzeige da?" legte beim Start ein Fenster an und zerstörte es sofort wieder. Danach lässt sich die Tk-Grafikschicht unter Windows nur noch unzuverlässig neu hochfahren – ein späteres Fenster scheitert dann mit einer Meldung über eine nicht lesbare `init.tcl`. Welcher Test es trifft, war Zufall.

**Ein fest erwarteter deutscher Text.** Ein Test verlangte wörtlich „BENUTZERHANDBUCH". Das Programm übernimmt beim Start aber die zuletzt gemerkte Sprache – wer es auf Englisch verlassen hatte, bekam einen roten Test, der mit der geprüften Sache nichts zu tun hatte.

**Ein zurückgezogenes Fenster und dein Hintergrundbild.** Drei weitere Tests übersprangen sich selbst, wenn gerade keine Beschriftung sichtbar war oder kein Hintergrundbild geladen. Beides hing an der Reihenfolge der Testdateien und an deinen Einstellungen, nicht am Prüfgegenstand.

Der Gesamtlauf liefert jetzt dreimal hintereinander dasselbe Ergebnis: 1155 Prüfungen grün, drei übersprungen – und diese drei mit Absicht (zwei Integrationstests, die man eigens einschalten muss, und einer, der nur auf Dateisystemen mit Groß- und Kleinschreibung gilt).

## v1.8.74 – 21.08.2026

### Keine Verbindungen mehr ohne dein Zutun

Fehlten in einem Backup Titel, Publisher oder Kategorie, hat das Programm sie bisher **ungefragt** nachgeschlagen – bei store.playstation.com, prosperopatches.com bzw. orbispatches.com, und über einen Umweg auch bei duckduckgo.com. Dabei ging die Title-ID des Spiels nach draußen, beim Umweg sogar der ausgeschriebene Titel. Unter Windows fällt das nicht auf, weil dort nichts nachfragt; auf einem Mac mit Firewall meldet sich jede dieser Verbindungen.

Das passiert jetzt nicht mehr von allein. Fehlt etwas, erscheint in der Spiel-Info ein Knopf **„Fehlende Angaben online nachschlagen“**. Erst der Klick baut eine Verbindung auf, und danach ist wieder zu. Fehlt nichts, erscheint der Knopf gar nicht.

Wer es lieber automatisch hätte, findet in den Einstellungen unter **METADATEN AUS DEM NETZ** ein Kästchen dafür. Ab Werk ist es leer. Darunter stehen die gefragten Dienste beim Namen.

Einmal geholte Angaben liegen weiterhin 30 Tage lokal und kosten keine zweite Verbindung. Unverändert bleiben: die Aktualisierungsprüfung, die Download-Verwaltung, die Verbindungen zu deiner PS5 und der Nachschlag bei defekter `param.json` – die laufen alle erst auf Knopfdruck, teils mit eigener Rückfrage.

### Das PS4-Fenster sagt jetzt, wohin das Abbild gehört

Ein umrandeter Kasten über „ABBILD ERSTELLEN“ mit dem, was an der Konsole gemessen wurde:

* **Direkt nach `/mnt/usb0/`** – Unterordner werden nicht durchsucht. Ein Abbild in `/mnt/usb0/ps4ffpsc/` wird nie gefunden.
* **Nicht nach `/data/homebrew` oder `/data/etaHEN/games`** – von dort gestartet gibt es einen Kernel Panic, die PS5 schaltet ab.
* **Nach so einem Absturz** bleibt ein leerer Eintrag zurück; erst die Kachel auf der PS5 löschen, sonst wird das Abbild auch am richtigen Ort nicht mehr gefunden.

Der bisherige Hinweistext desselben Fensters empfahl ausgerechnet den Unterordner, in dem nichts gefunden wird. Das ist korrigiert.

### Bei schmalem Fenster passt die obere Zeile wieder

In v1.8.73 ragte sie bei der kleinsten Fenstergröße um einen Pixel über die Karte hinaus – die Bildlaufleiste nimmt 15 Pixel, die in der Rechnung fehlten. Die Mindestbreite steht deshalb jetzt auf 1245 statt 1230 Pixeln.

## v1.8.73 – 21.08.2026

### Das Bedienfeld unter ZIELFORMAT ist aufgeräumt

Der Bereich mit Zielformat, Kompression und den Einbau-Optionen sah unordentlich aus, ohne dass man sagen konnte warum. Nachgemessen waren es vier Dinge:

**Nichts stand auf einer Linie.** Die fünf Elemente der Zeile „BEIM ERSTELLEN EINBAUEN“ waren über sechs Pixel verteilt – das AMPR-Kästchen vier Pixel tiefer als seine Klappliste daneben. Jetzt sitzen sie exakt auf einer Höhe, und zwar auch dann noch, wenn du die Sprache oder das Design wechselst oder mit einer anderen Bildschirmskalierung arbeitest.

**Eine Überschrift für drei Felder.** Über Kompression, Worker-Anzahl und Prüfstufe stand eine einzige lange Zeile: „KOMPRESSION (PFS) / WORKER-THREADS / PRÜFUNG“. Welches Wort zu welchem Kasten gehört, war nicht zu erkennen. Jetzt trägt jedes Feld seine eigene Beschriftung direkt über sich.

**Ungleiche Abstände.** In derselben Zeile waren es 5, 8, 15 und wieder 5 Pixel. Jetzt gilt überall dieselbe Regel: **eng** heißt „gehört zusammen“ (ein Kästchen und die Klappliste, die nur dazu gehört), **weit** heißt „ist eine eigene Einstellung“.

**Der Hinweistext klebte** mit einem einzigen Pixel Abstand an den Kästchen darüber. Jetzt hat er Luft.

### Bei breitem Fenster rückt die Einbau-Zeile nach oben

Rechts neben „PRÜFUNG“ blieb bisher viel Fläche leer, während sich AMPR EMU, PlayGo und BACKPORT eine Zeile weiter unten drängten. Ist das Fenster breit genug – ab etwa 1780 Pixeln –, stehen sie jetzt oben in derselben Zeile. Die Karte wird dadurch **66 Pixel niedriger**, und unten bleibt mehr Platz für das Protokoll.

Wird das Fenster schmaler, rutscht die Zeile von allein wieder an ihren alten Platz. Das ist keine Kosmetik: Ohne diesen Rückfall stünde BACKPORT bei schmalem Fenster außerhalb der Karte – sichtbar wäre es nicht, anklickbar auch nicht.

An dem, was das Programm mit deinen Dateien macht, ändert sich nichts.


## v1.8.72 – 21.08.2026

### .ffpkg läuft jetzt auch unter macOS und Linux

Bisher stand im Programm, das Erzeugen und Lesen einer `.ffpkg` gehe nur unter Windows. Das stimmte so nicht: Das dafür verwendete UFS2Tool läuft auf allen drei Systemen – es lag bei uns nur der Windows-Bau bei. Jetzt liegt für jedes System einer bei.

Einzig das **Einhängen einer .ffpkg als Laufwerk** bleibt Windows vorbehalten, weil es den Dokan-Treiber braucht. Unter macOS und Linux wird stattdessen direkt entpackt – das Ergebnis ist dasselbe.

### Kein installiertes .NET mehr nötig

Der bisher mitgelieferte Windows-Bau setzte stillschweigend voraus, dass auf deinem Rechner **.NET 8** installiert ist. Fehlte es, schlug jeder `.ffpkg`-Vorgang fehl, ohne dass irgendwo stand warum. Die neuen Bauten bringen alles mit, was sie brauchen.

Das Programm wächst dadurch um rund 11 MB.

### Der Diagnosebericht führt UFS2Tool als mitgeliefert

Mit Fassung, Plattform und Quelle – und die Aktualisierungsprüfung fragt es damit mit ab. Aus der Liste der Werkzeuge, die du selbst installieren musst, ist es verschwunden.

## v1.8.71 – 21.08.2026

### Bei kurzen Fenstern fällt nichts mehr aus dem Bild

Der Inhalt rechts braucht zusammen rund 1356 Pixel Höhe. Die Protokollfläche gibt nach und fängt das normalerweise auf – alles andere ist starr. War das Fenster kürzer als etwa 880 Pixel, stand der Rest einfach unter dem Fensterrand: Bei 768 Pixeln fehlten **STARTEN und ABBRECHEN**, nicht verkleinert, sondern außerhalb und nicht anklickbar. Auf einem 1366×768-Bildschirm traf das jeden.

Der Inhalt lässt sich jetzt rollen – mit Mausrad oder Bildlaufleiste. Reicht der Platz, ändert sich nichts: Die Leiste bleibt ausgeblendet und alles sitzt wie bisher.

### Der Diagnosebericht nennt die mitgelieferten Werkzeuge

Ein neuer Abschnitt listet Fassung und Herkunft von allem, was das Programm mitbringt – MkPFS, das PS4-Werkzeug, die AMPR-EMU-Bibliotheken, die Backport-Fakelibs, die Nutzlasten – dazu die gefundenen Fremdwerkzeuge und die Python-Bibliotheken. Das steht in jedem Bericht und braucht kein Internet.

### Neuer Knopf: Aktualisierungen prüfen

Im Diagnosefenster fragt ein Knopf die Quellen ab und schreibt unter den Bericht, wo es etwas Neueres gibt. Das läuft nur auf Knopfdruck – ein Fehlerbericht soll nicht an einer Internetverbindung hängen.

Mitgeprüft wird auch **AMPR EMU** – das Projekt veröffentlicht seine Fassungen auf GitHub.

Nicht alles hat eine abfragbare Quelle: FileZilla, OSFMount, die Fakelibs und die Nutzlasten veröffentlichen keine Fassungsliste. Dort steht, was vorliegt, und wo es herkommt.

## v1.8.70 – 21.08.2026

### Die Werkzeugleiste passt sich an, statt Knöpfe zu quetschen

Die dreizehn Knöpfe oben brauchen zusammen rund 1515 Pixel. War weniger da, hat sie das Programm nicht weggelassen, sondern zusammengedrückt – bei einem 1440 Pixel breiten Fenster war „BENUTZERHANDBUCH" noch 100 statt 189 Pixel breit, bei 1366 nur noch **26**. Lesen oder treffen konnte man ihn dann nicht mehr.

Reicht der Platz nicht, wandern einzelne Knöpfe jetzt ins Sammelmenü **WEITERE TOOLS**, wo sie unter einem Trennstrich stehen. Zieht man das Fenster wieder breiter, kommen sie an ihren Platz zurück. BEENDEN, DESIGN, EINSTELLUNGEN, WEITERE TOOLS und die Sprachumschaltung bleiben immer stehen.

### Die Statuszeile wird nicht mehr abgeschnitten

Die Zeile unten rechts nennt, was die gewählte Aufgabe tut. Sie brauchte 860 Pixel; bei schmalem Fenster standen 627 zur Verfügung, der Rest fehlte ohne jeden Hinweis. Sie bricht jetzt um.

### Kein Hintergrundbild wird mehr hochgerechnet

Eines der zwanzig Querformatbilder (`ray-burst`) war mit 1424 × 752 zu klein und wurde auf einem 1920er Bildschirm um 35 % hochgerechnet – es wirkte dadurch weich. Alle zwanzig Seitenleistenbilder waren 320 × 1000 und wurden um 54 % hochgerechnet.

Es liegen jetzt größere Fassungen bei: ein neues `ray-burst` in voller Größe und Seitenleistenbilder in 640 Pixeln Breite. Die übrigen neunzehn Querformatbilder sind unverändert.

### Das Fenster lässt sich nicht mehr schmaler als 1230 Pixel ziehen

Vorher 1200. Darunter passte die Überschrift „KOMPRESSION (PFS) / WORKER-THREADS / PRÜFUNG" nicht mehr in ihre Spalte.

## v1.8.69 – 20.08.2026

### Das Hintergrundbild sitzt jetzt vom ersten Moment an

Beim Öffnen des Fensters wurde das Hintergrundbild bisher **gar nicht auf die Fenstergröße gerechnet** – es blieb in der Größe der Bilddatei stehen, während Inhaltsfläche und Seitenleiste ihre Bilder längst angepasst hatten. Sichtbar wurde das als Bruch zwischen den Flächen, der erst verschwand, wenn man das Fenster einmal anfasste. Das Bild wird jetzt beim Start einmal nachgezogen.

Dasselbe beim **Wechsel des Designs**: Dabei meldet die Oberfläche für einen Augenblick eine Zwischengröße, und die dafür berechnete Fassung überschrieb kurz darauf die richtige. Auch das ist behoben – nach einem Designwechsel stimmen alle vier Flächen sofort.

### AMPR EMU und BACKPORT stehen jetzt in einer eigenen Zeile

Seit v1.8.68 standen acht Bedienelemente in einer Reihe – Kompression, Worker-Threads, Prüfstufe und die beiden Integrationen mit ihren Auswahllisten. Die Reihe braucht 1145 Pixel Breite, und so breit ist die Pfad-Karte nur bei einem Fenster ab rund 1725 Pixeln. Darunter standen die hinteren Bedienelemente außerhalb der Karte: nicht zu sehen und nicht anzuklicken. Bei 1366 Pixeln fehlten 352 Pixel.

**AMPR EMU und BACKPORT haben jetzt eine eigene Zeile** darunter, mit der Überschrift „BEIM ERSTELLEN EINBAUEN". Alles passt damit auch in schmale Fenster.

Zwei Folgen davon:

- Das Fenster lässt sich nicht mehr schmaler als 1200 Pixel ziehen (vorher 1100). Bei 1100 fiel schon die Prüfstufen-Liste aus der Karte heraus.
- Die Pfad-Karte ist 66 Pixel höher. Bei einem Fenster unter rund 860 Pixeln Höhe steht die Knopfleiste unten hinaus.

### Die Einstellungen nennen die Maße, die dein Bildschirm braucht

Bei der Bildauswahl stand bisher eine feste Zahl. Die stimmt aber nur für einen Bildschirm: Wie breit die Seitenleiste wirklich ist, hängt an deiner Anzeigeskalierung – bei 125 % sind es rund 500 statt der angegebenen 320 Pixel. Der Hinweis rechnet die nötige Größe jetzt für deinen Bildschirm aus.

Ein zu kleines Bild wird weiterhin angenommen, es wirkt dann nur weich gezogen. Verzerrt wird nie: Überstand wird mittig beschnitten.

### Der Diagnosebericht prüft die Darstellung mit

Ganz oben steht jetzt eine Urteilszeile, dazu kommen zwei neue Abschnitte. Geprüft werden zusammengedrückte und abgeschnittene Bedienelemente, zu enge Beschriftungen, hochgerechnete oder stehengebliebene Hintergrundbilder, die Anzeigeskalierung samt Schriftgröße sowie Arbeitsspeicher, angesammelte Bilder und Zeitgeber und die Reaktionszeit des Fensters. Steht dort „keine Auffälligkeit", ist die Oberfläche in Ordnung – sonst nennt jede Zeile das betroffene Element und die gemessenen Zahlen.

## v1.8.68 – 20.08.2026

### AMPR EMU und BACKPORT lassen sich beim Erstellen mit einbauen

In der Zeile mit Kompression und Worker-Threads stehen zwei neue Kästchen – dort, wo bisher nur „PRÜFUNG NACH DEM PACKEN" stand. Was du dort ankreuzt, fließt beim Erstellen gleich mit ins Backup:

- **AMPR EMU** legt die gewählte `libSceAmpr.sprx` in den fakelib-Ordner und baut danach `ampr_emu.index` neu. Die Version wählst du daneben aus – zwanzig stehen zur Verfügung, von 0.2.6 bis 0.3.5.1, jeweils mit und ohne Protokollausgabe.
- **PlayGo** ist ein eigenes Häkchen daneben. Wie im AMPR-Manager ist es nicht vorausgewählt: `libScePlayGo.sprx` stammt aus einem anderen Projekt und wird nur gebraucht, wenn ein Titel Inhalte als fehlend behandelt.
- **BACKPORT** setzt die SDK-Angaben aller Programmdateien auf die gewählte Firmware herab und legt die passenden Ersatzbibliotheken dazu. Angehoben wird nie – Dateien, die schon unter der Zielversion liegen, bleiben unberührt.

Beide Kästchen lassen sich zusammen ankreuzen. Dann läuft erst der Backport und danach der AMPR EMU – in dieser Reihenfolge, weil beide in denselben fakelib-Ordner schreiben.

**Das wirkt auf jedes Zielformat**: .ffpfsc, .ffpfs, .exFAT, .ffpkg und den Dump-Ordner. Egal, welchen Weg du gehst – am Ende entsteht jedes Backup aus einem Dump-Ordner, und genau dort wird eingebaut.

**Wenn deine Quelle ein Dump-Ordner ist** (Aufgabe 1), fragt das Programm vorher, ob es eine Arbeitskopie anlegen soll. Sagst du ja, bleibt dein Original unberührt – das kostet einmal denselben Platz. Sagst du nein, wird direkt in deinem Ordner gearbeitet; ersetzte Dateien bleiben dabei als `.orig` liegen. Kommt die Quelle aus einem Container, entfällt die Frage: Dort wird ohnehin in einen Arbeitsordner ausgepackt.

### Repariert

- **Die Liste der AMPR-Versionen zeigte die falsche als neueste.** „0.3.5" stand vor „0.3.5.1", und damit war beim Öffnen die ältere vorausgewählt. Das betraf auch den AMPR-EMU-Manager (Aufgabe 7).
- **PlayGo wurde nie gefunden.** Gesucht wurde nach derselben Versionsnummer wie beim AMPR-Modul – die es dort nie gibt, weil `libScePlayGo.sprx` aus einem eigenen Projekt stammt und getrennt zählt. Jetzt entscheidet die Variante: ohne Protokollausgabe bekommt „nolog", mit bekommt „log".

## v1.8.67 – 20.08.2026

### Jede Bauart einer .ffpfsc wird vollständig entpackt

Eine `.ffpfsc` kann auf mehrere Arten gebaut sein, und man sieht es der Datei von außen nicht an. Bisher packte das Programm höchstens **eine** Ebene tief aus. Steckte eine Ebene mehr darin, landete eine einzelne `.exfat`-Datei im Dump-Ordner – und gemeldet wurde trotzdem Erfolg. Das Backup war unbrauchbar, ohne dass etwas darauf hindeutete.

- **Aufgabe 2 und Aufgabe 4 packen jetzt Ebene für Ebene aus, bis die Spieldateien erscheinen.** Woran erkannt wird, was in der nächsten Ebene steckt: an der Kennung des Abbilds, nicht an seinem Namen oder seiner Endung. Damit sind alle vier Bauarten abgedeckt – auch die von `mkpfs pack folder` ohne `--raw`, bei der ein exFAT-Abbild zwischen Container und Spieldateien liegt.
- **Zum Schluss wird nachgezählt.** Dateien und Bytes werden gegen die Werte gehalten, die im Abbild stehen. Fehlt etwas, bricht die Aufgabe mit dem genauen Fehlbetrag ab, statt einen halben Ordner als fertig zu melden.
- **Gleichnamige Ordner werden beim Verschieben zusammengeführt** statt ineinandergelegt, und ein misslungenes Verschieben lässt die Aufgabe fehlschlagen. Vorher wurde es nur ins Protokoll geschrieben – und der Ordner, in dem die Dateien noch lagen, unmittelbar danach gelöscht.
- **Der Platzbedarf halbiert sich:** Jedes ausgepackte Abbild wird gelöscht, sobald seine Ebene fertig ist.
- **Aufgabe 7 (AMPR EMU Manager) ging denselben Weg** und zeigte bei so einem Container eine einzelne `.exfat` statt des Dump-Inhalts an. Auch sie packt jetzt vollständig aus.

### Neben QUELLE steht, wie der Container gebaut ist

Sobald eine `.ffpfsc` oder `.ffpfs` als Quelle anliegt, steht rechts daneben, was darin steckt – etwa "exFAT-Innenabbild (mkpfs pack folder/pack file)" oder "PFS-Innenabbild (Aufbau dieses Programms)". Ist eine Ebene zu viel darin, erscheint das in Orange; ein Tooltip erklärt, was das bedeutet und wie man es richtig baut. Geprüft wird im Hintergrund, gelesen werden dabei nur Kopf und Verzeichnisse, nie die Nutzdaten.

### .ffpfsc und .ffpfs lassen sich ineinander umwandeln

Beide Richtungen waren gesperrt, mit dem Hinweis "lässt sich nicht nachträglich entpacken". Das stimmte einmal, seit dem vollständigen Auspacken aber nicht mehr: Der Weg ist derselbe wie zu `.ffpkg` – erst in den Dump-Ordner, dann neu bauen. Aufgabe 2 bietet die beiden Formate jetzt an.

### Neu: PS4 PKG zu ffpfsc

Unter **WEITERE TOOLS** gibt es einen neuen Eintrag. Er führt PS4-PKG – Basisspiel, Patches und wahlweise DLC – oder ein bereits entpacktes PS4-Spiel zu einem ShadowMountPlus-Abbild zusammen, wahlweise als `.ffpfsc` oder als unkomprimiertes `.exfat`. Die Arbeit macht das eingebettete PS4 FFPFSC 0.2.8; die Oberfläche ist die dieses Programms, auf Deutsch und Englisch, mit Fortschritt, Protokoll und Abbruch.

Drei Fehler des Werkzeugs sind dabei aufgefallen und behoben:

- **Es verlangte einen Compiler und CMake**, obwohl der fertige PKG-Entpacker daneben liegt – und meldete deshalb immer "nicht bereit".
- **Ein Absturz des Entpackers galt als "PKG nicht unterstützt".** Beim Prüfen einer PKG mit Prüfsumme bricht er ab; der Rückgabewert wurde nicht angesehen, und heraus kam ein Fehler in der Datei statt einer im Werkzeug. Jetzt wird ohne Prüfsummenlauf wiederholt und diese selbst nachgerechnet.
- **Zu lange Arbeitspfade ließen das Entpacken scheitern** ("Failed to write extracted PKG entry"). Wird der Arbeitsordner zu tief, weicht das Programm auf einen kurzen Pfad aus und schreibt es ins Protokoll. Das fertige Abbild landet trotzdem im gewählten Zielordner.

Was die Vorlage als bekannte Einschränkung nennt, bleibt bestehen: Manche Spiele scheitern auf der Konsole an der Trophäenregistrierung (`errcode=0x80551618`), und die DLC-Einbettung ist ausdrücklich experimentell – sie ist deshalb standardmäßig aus und fragt vor dem Start nach.

## v1.8.66 – 20.08.2026

### Die Mac-Fassung sieht aus wie die Windows-Fassung

- **Die Schrift ist auf dem Mac so groß wie unter Windows.** Bisher stand die gesamte Oberfläche dort bei rund 60 % der gewohnten Größe – Titelleiste, Aufgabenknöpfe, Beschriftungen auf der Karte, Eingabefelder, Protokollfläche. Neun Punkt ergeben jetzt fünfzehn Bildpunkte statt neun, zwölf Punkt zwanzig statt zwölf.
- **Die Knöpfe tragen wieder ihre eigene Farbe.** Die Reihe oben von BENUTZERHANDBUCH bis BEENDEN erschien auf dem Mac als Reihe heller Kästen, und die beiden Knöpfe unten links in der Seitenleiste waren gar nicht mehr zu entziffern: helle Schrift auf hellem Grund. Beides ist behoben.

### Repariert

- **„FileZilla gestartet" blieb unten rechts stehen, bis etwas anderes die Zeile überschrieb** – auch dann noch, wenn FileZilla längst wieder geschlossen war. Die Meldung verschwindet jetzt von selbst: mit dem Programm, sobald es sich beenden lässt, sonst nach zehn Sekunden.

## v1.8.65 – 20.08.2026

### Repariert

- **Wer das Bibliotheksfenster schließt, während es noch sucht, löste im Hintergrund einen Absturz aus.** Zu sehen war davon nichts – das Programm lief weiter –, aber im Fehlerbericht stand ein Absturz, der keiner war. Dasselbe galt für den Protokollempfänger des JS-Loaders.

Beide melden ihr Ergebnis jetzt nur noch dann ins Fenster zurück, wenn es das Fenster überhaupt noch gibt. Fünf neue Prüfungen sichern das ab, eine davon aus einem echten Arbeitsfaden heraus – im Hauptfaden tritt der Fehler gar nicht auf.

## v1.8.64 – 20.08.2026

### Repariert

- **Das Kästchen „Rechner nach erfolgreichem Abschluss herunterfahren" wurde beim Wechsel des Farbschemas wieder grau.** Beim Start trug es die helle Schrift aus v1.8.63, nach dem ersten Wechsel von Dunkel auf Hell oder Mittel nicht mehr. Zwei Stellen im Programm setzten dieselbe Farbe, die zweite überschrieb die erste.

Zwei neue Prüfungen sichern das ab: Eine schaltet durch alle drei Farbschemata und wieder zurück und misst nach jedem Schritt die Schriftfarbe aller zehn Beschriftungen; die zweite verbietet die überschreibende Zeile ausdrücklich.

## v1.8.63 – 20.08.2026

### Lesbarkeit auf der Karte

- **Alle Texte auf der Karte sind jetzt hell geschrieben** – QUELLE, ZIELFORMAT, die Zeilenüberschrift, der Formathinweis, ZIELORDNER, TEMP-ORDNER und das Kästchen zum Herunterfahren. Bisher waren sie gedämpft grau; auf einer einfarbigen Fläche wirkt das ruhig, auf dem Hintergrundbild verschwanden sie dort, wo das Motiv hell wird.
- **Die Statuszeile und die Telemetriezeile darunter ebenso** – sie liegen auf demselben Bild und hatten dasselbe Problem.
- **Die Karte lässt 10 Prozentpunkte weniger vom Hintergrundbild durch** (40 statt 50 %). Das Motiv bleibt deutlich sichtbar, liegt der Schrift aber nicht mehr im Weg.

### Repariert

- **Beim Wechsel des Farbschemas wären zwei Aufhellungen wieder verschwunden.** „PRÜFUNG NACH DEM PACKEN" und das Kästchen zum Herunterfahren fehlten in der Tabelle, aus der die Schriftfarben nach einem Design-Wechsel nachgezogen werden.

## v1.8.62 – 19.08.2026

### Anzeige

- **„PRÜFUNG NACH DEM PACKEN" war schwer zu lesen.** Die Beschriftung sitzt rechts neben der Klappliste und damit über der hellsten Stelle der üblichen Hintergrundbilder. Sie ist jetzt hell geschrieben statt gedämpft wie die Beschriftungen daneben, die über dunklen Bereichen liegen.
- **Das Fenster ps5_autoloader ging viel zu breit auf** – gemessen 1651 statt der eingestellten 980 Pixel, weil die sieben Knöpfe nebeneinander so viel Platz verlangen. Auf einem kleineren Bildschirm wären die hinteren wieder abgeschnitten gewesen. Jetzt zwei Knopfreihen.
- **Dem Fenster ps5_autoloader fehlte die Überschrift**, die jedes andere Werkzeugfenster innen trägt. Es fing mitten im Hinweistext an.

## v1.8.61 – 19.08.2026

### Download-Fenster

- **Der Rechtsklick in einem Eingabefeld tat nichts.** Belegt war er nur auf dem Hauptfenster (Vollbild, Verkleinern, Beenden); Nebenfenster sind eigene Toplevels und erben das nicht. Ausgerechnet im Feld für Download-Adressen war er der naheliegende Weg – und der einzige, der nicht funktionierte. Jedes Textfeld im ganzen Programm hat jetzt „Ausschneiden / Kopieren / Einfügen / Alles markieren", auf dem Mac auch über Strg+Klick.
- **Mehrere Adressen auf einmal.** Sie wurden schon vorher alle erkannt, aber jede unbrauchbare Zeile öffnete ein eigenes Hinweisfenster – bei einem aus einer Seite kopierten Block mehrere hintereinander, hinter denen die Liste verschwand. Jetzt eine Zeile im Protokoll: wie viele übernommen, wie viele schon dastanden.
- **Zwischenablage überwachen.** Ist der Haken gesetzt, genügt im Browser der Rechtsklick auf den Download-Link und „Linkadresse kopieren" – die Adresse landet von selbst in der Liste und wird geladen. Die Überwachung läuft **auch bei geschlossenem Download-Fenster** und schon ab dem Programmstart; wird eine Adresse gefunden, öffnet sich das Fenster von selbst. Den Haken gibt es an zwei Stellen – im Download-Fenster und in den Einstellungen –, beide schalten dasselbe. Die Einstellung bleibt erhalten.
- **Dieselbe Adresse zweimal ergibt keinen zweiten Eintrag mehr.** Bisher blockierte nur, was gerade wartete oder lief; fertige und schon vorhandene Dateien wurden erneut aufgenommen. Fehlgeschlagene und abgebrochene bleiben ausgenommen – die soll man erneut anstoßen können.
- **Strg+Eingabe** schließt das Einfügefenster ab. Die bloße Eingabetaste kann es nicht sein: In einem mehrzeiligen Feld gehört sie zum Zeilenumbruch, und mehrere Zeilen sind hier der Normalfall.

### Backport – Deckung prüfen

- **Neu: „Deckung prüfen".** Bisher hieß „backportiert" nur, dass die Ersatzbibliotheken im Ordner liegen. Ob eine davon überhaupt liefert, was das Spiel von ihr verlangt, sah niemand nach – auf der Konsole fällt es erst beim Start auf, und dann ohne brauchbare Meldung. Das Programm liest jetzt die Importe des Spiels und die Exporte der Ersatzbibliotheken und schreibt ins Protokoll, welche Funktionen fehlen. Bibliotheken, die von der Konsole kommen, werden getrennt aufgeführt und nicht als Befund gemeldet.

### Neu: ps5_autoloader

- **Ein Fenster für die Startreihenfolge der Konsole** (WEITERE TOOLS → ps5_autoloader). Es liest und schreibt `/data/ps5_autoloader` über FTP: `autoload.txt` bearbeiten, Payloads hochladen und löschen, den ganzen Ordner als Schnappschuss sichern und zurückspielen.
- Beim Schreiben wird gewarnt, wenn die `autoload.txt` Dateien nennt, die gar nicht im Ordner liegen – die Konsole überspringt solche Zeilen stillschweigend.
- Nach dem Hochladen wird nachgesehen, ob die Datei das Ausführungsrecht trägt. Ohne das startet die Konsole sie nicht und sagt nichts dazu.

## v1.8.60 – 19.08.2026

### Die Knöpfe sind wieder erreichbar

- **In elf von vierzehn Werkzeugfenstern lag die unterste Knopfreihe außerhalb des Fensters.** Man musste es erst größer ziehen, um an „Schließen“ oder „Umbenennen“ zu kommen. Betroffen waren unter anderem der AMPR-Index-Builder (es fehlten 265 Pixel Höhe), die Bibliothek, der PKG-Merger, der Diagnosebericht, das KLOG-Fenster und „Dump umbenennen“.
- **Jedes Fenster richtet sich jetzt nach seinem Inhalt.** Die Größe wird beim Öffnen angepasst, der Bildschirm ist die Grenze. Wer ein Fenster von Hand vergrößert, behält das wie bisher.

### Anzeige

- **Die Protokollfläche lässt 30 % des Hintergrundbildes durchscheinen.** Bisher war sie fast deckend.
- **Die Knopfleiste unter der Karte ebenfalls.** Die Leiste mit „Starten“, „Abbrechen“ und der Größenanzeige zeigte das Hintergrundbild unverändert; neben der Karte darüber wirkte das Motiv dadurch wie gespiegelt. Auch dort trägt jetzt die Flächenfarbe, das Bild scheint zu 30 % durch.
- Eine Meldung beim Umbenennen eines Dump-Ordners hatte ein falsches schließendes Anführungszeichen.
- **Das Hintergrundbild sprang an der Kartenkante.** Die Karte zeichnete ihren Untergrund aus einem gestreckten Bild, während die Fläche darunter seit v1.8.55 formatfüllend beschnitten wird – dadurch tauchte das Motiv versetzt ein zweites Mal auf. Beide benutzen jetzt dieselbe Geometrie.
- **Das dritte Feld in der Bedienzeile hat jetzt eine Beschriftung.** Bisher stand dort nur „Schnell“, ohne dass erkennbar war, worum es geht. Rechts daneben steht jetzt „PRÜFUNG NACH DEM PACKEN“, und die Zeilenüberschrift nennt alle drei Felder.
- **Das Zahlenfeld für die Worker-Threads ist so hoch wie die Klapplisten daneben.** Es saß sichtbar tiefer und wirkte wie hineingerutscht.

### Neue AMPR-EMU-Fassungen

- **0.3.1, 0.3.4 und 0.3.5 liegen bei** und stehen im AMPR EMU Manager (Aufgabe 7) ganz oben zur Auswahl. Am Programm war dafür nichts zu ändern – der Versionsspeicher wird eingelesen, nicht aufgezählt.

---

## v1.8.59 – 19.08.2026

### Erstinstallation auf dem Mac

- **Im Abbild liegt jetzt „Erste Installation.command“.** Ein Doppelklick legt das Programm in den Programme-Ordner und entfernt die Markierung „aus dem Internet geladen“. Danach startet es ohne die Warnung von macOS. Nötig ist das **einmal pro heruntergeladener Fassung**, nicht bei jedem Start.
- Dazu eine Verknüpfung auf den Programme-Ordner für alle, die lieber ziehen.
- **Das Programm merkt jetzt, wenn macOS es aus einem Schattenordner startet.** Das passiert, solange die Markierung noch dran ist – Einstellungen und Protokolle gehen dann beim Beenden verloren. Statt merkwürdigem Verhalten gibt es einen Hinweis mit der Lösung.

### Schrift auf dem Mac

- **Deutlich größer.** Die bisherige Vergrößerung war zu vorsichtig geschätzt; am Diagnosebericht nachgerechnet ergibt sich dieselbe Zeichenhöhe wie unter Windows. Wer es anders möchte, ändert weiterhin `macos_font_scaling` in der Einstellungsdatei.
- Der Diagnosebericht nennt zusätzlich, in welcher Größe die Hintergrundbilder tatsächlich gezeichnet wurden – bisher stand dort nur, welche Bilddatei geladen ist.

---

## v1.8.58 – 19.08.2026

### Fehler verschwinden nicht mehr

- **Ein Fehler in der Oberfläche war bisher unsichtbar.** Das Programm läuft ohne Konsolenfenster; Tkinter schreibt Fehler aus Knöpfen und Tastenbindungen aber genau dorthin. Es gab keinen Protokolleintrag und keine Meldung – der Knopf tat einfach nichts. Solche Fehler landen jetzt im Protokoll, mit einer kurzen Zeile im Konsolenfenster.
- Dasselbe gilt für Fehler in den **Hintergrundvorgängen**, die während einer Umwandlung laufen.

### Die Diagnose sagt jetzt etwas über die Anzeige

- Der Bericht enthält sechs neue Abschnitte: **Anzeige** (Bildschirmgröße, DPI, Skalierung, Schriftarten, Design, Hintergrundbild), **Laufzeitumgebung**, gefundene **Fremdwerkzeuge**, **freier Speicherplatz** auf Quelle, Ziel und Temp, die **Fehler dieser Sitzung** und die letzten Zeilen der **Protokolldatei**.
- Damit lässt sich ein Anzeigefehler einordnen, den man nur sieht: Ein Bildschirmfoto zeigt, *dass* etwas falsch aussieht, der Bericht sagt, *warum*.
- Die Suche nach Fremdwerkzeugen wird dabei **nicht** neu angestoßen – der Bericht soll sofort da sein, nicht nach Minuten.

---

## v1.8.57 – 19.08.2026

### Ein Hinweis vor der Formatwahl

- **Unter der Zielformat-Liste steht jetzt, was ein PFS-Container kostet:** Die PS5 entpackt `.ffpfsc` und `.ffpfs` mit rund 150–250 MB/s – etwa ein Drittel eines USB-Laufwerks und ein Zehntel der internen SSD. Spiele, die viel nachladen oder Texturen streamen, können dadurch ruckeln. Bei `.exfat`, `.ffpkg` und Ordner-Zielen erscheint der Hinweis nicht.
- Er erscheint auch dann, wenn man **nur das Format** umstellt und nicht die Aufgabe – vorher hing der Text allein an der Aufgabenwahl.

---

## v1.8.56 – 19.08.2026

### Prüfung nach dem Packen ist wählbar

- **Neues Feld „PRÜFUNG“ neben den Worker-Threads** mit drei Stufen. *Schnell* ist voreingestellt: Das Packwerkzeug sieht sich das fertige Abbild noch einmal an, bevor es als fertig gilt. *Vollständig* liest es zusätzlich komplett zurück und dauert deutlich länger. *Aus* entspricht dem bisherigen Verhalten.
- **Bisher lief gar keine dieser Prüfungen.** Das Programm hat sie an sechs Stellen abgeschaltet – nicht sichtbar, nicht abwählbar. Die offizielle Anleitung zum Packen und das Referenzprogramm lassen sie laufen.
- Die Einstellung bleibt erhalten und übersteht einen Sprachwechsel.

---

## v1.8.55 – 19.08.2026

### Vier Befunde vom Mac

- **Ein Klick auf FileZilla ließ das Programm abstürzen.** Im Dateidialog stand ein Dateiname als Suchmuster. Windows kommt damit zurecht, macOS nicht – dort bricht das Betriebssystem das Programm ab, ohne eine Meldung zu zeigen. Dieselbe Ursache steckte ein zweites Mal im SELF-Inspektor; beide Stellen sind behoben, und eine Prüfung geht jetzt über alle Dateidialoge des Programms.
- **FileZilla wurde auf dem Mac nie gefunden**, auch wenn es installiert war: Gesucht wurde nur nach der Windows-Datei. Jetzt kennt das Programm auch `FileZilla.app` und die üblichen Linux-Pfade – und startet sie richtig.
- **Das Hintergrundbild wird nicht mehr verzerrt.** Es wurde bisher auf die Fenstergröße gestreckt; passte das Seitenverhältnis nicht, sah man es. Jetzt füllt es die Fläche formatfüllend aus und wird mittig beschnitten, wie ein Bildschirmhintergrund. Im Vollbild wurde es zuvor gar nicht angepasst.
- **Die Schrift ist auf dem Mac deutlich größer.** Dieselbe Punktangabe ergibt dort rund ein Drittel weniger Pixel als unter Windows. Knöpfe wachsen mit. Wem es noch nicht reicht, kann den Faktor in der Einstellungsdatei ändern (`macos_font_scaling`).

---

## v1.8.54 – 19.08.2026

### Zwei Fehler aus v1.8.53

- **Aufgabe 8 meldete FEHLGESCHLAGEN, obwohl alles in Ordnung war.** Die `param.json` steht in der Liste der unverzichtbaren Dateien. Fehlte sie, fiel das Urteil – und erst danach wurde angeboten, sie anzulegen. Im Protokoll stand dann „param.json wurde neu erstellt, Prüfung bestanden“ und darüber ein rotes Fehlerfenster. Die Datei wird jetzt vor der Prüfung behandelt.
- **Die Rückfrage stand auf Ja, obwohl ein Ja ins Netz greift.** Bis v1.8.52 hatte der Online-Nachschlag eine eigene Frage mit vorbelegtem Nein. Beim Zusammenlegen der beiden Fragen ging das verloren, und ein versehentliches Enter schickte die Titel-ID an prosperopatches.com. Führt ein Ja zu einem Netzabruf, steht der Knopf wieder auf Nein.

### Kleinere Berichtigungen

- **„Die Konvertierung ist fehlgeschlagen“** erschien auch bei Aufgabe 8 und der Inspektion – beide wandeln nichts um, sie lesen. Der Hinweis auf einen mkpfs-Exit-Code verwies dort auf einen Schritt, den es nicht gibt. Sie melden jetzt „Beanstandungen gefunden“.
- **Diese Fehlermeldungen waren als einzige noch fest auf Deutsch verdrahtet.** Im englischen Programm stand hier deutscher Text; jetzt zweisprachig wie der Rest.

---

## v1.8.53 – 18.08.2026

### Die param.json entsteht jetzt aus dem Backup selbst

- **Der Spielname kommt aus den Trophäen.** Im Container `sce_sys/trophy2/trophy00.ucp` steht er als lesbarer Text – bisher konnte ihn nur der Online-Nachschlag liefern.
- **Die Inhaltsversion kommt aus `sce_sys/pfs-version.dat`.** Dort steht, welcher Spielstand im Backup liegt, zum Beispiel `01.002.000` bei einem aktualisierten Spiel. Bisher wurde immer `01.000.000` eingetragen – bei einem gepatchten Spiel falsch, ohne dass man es der Datei ansieht.
- **Die Titel-ID wird zusätzlich in der `eboot.bin` gesucht**, falls `sce_sys/nptitle.dat` fehlt. Anders als der Ordnername lässt sie sich dort nicht versehentlich ändern.
- **Nur noch eine Bestätigung statt drei.** Der Online-Nachschlag für die Content-ID läuft gleich mit; dass dabei die Titel-ID an prosperopatches.com geht, steht in der einen Frage.
- **Die erzeugte Datei besteht jetzt die eigene Prüfung.** Seit v1.8.51 meldete ausgerechnet die selbst erstellte `param.json` Fehler: Zwei Pflichtfelder fehlten, und die Inhaltsversion stand im Format der Master-Version.

---

## v1.8.52 – 18.08.2026

### Drei Dinge, die man sieht

- **Das helle Design ist wieder hell.** Das Hintergrundbild ist dunkel gehalten und wurde bisher in jedem Design gleich stark eingemischt. Im hellen Design saßen helle Karten und Knöpfe dadurch vor fast schwarzem Grund, und Beschriftungen lagen je nach Stelle auf hellem oder dunklem Untergrund. Jetzt bleibt das Bild dort ein dezentes Wasserzeichen.
- **Kein fremdes Symbol mehr beim Start.** Für etwa eine Sekunde stand das Standardsymbol von Tkinter in der Taskleiste, bevor das richtige erschien. Das eigene Symbol wird jetzt gesetzt, sobald das Fenster entsteht.
- **Tabellenüberschriften sitzen über ihren Werten.** In allen Tabellen – param.json-Editor, Bibliothek, PKG-Merger, MicroMount und ShadowMount+ – waren die Überschriften zentriert, die Werte darunter linksbündig. Bei einem breit gezogenen Fenster standen sie weit auseinander.

---

## v1.8.51 – 18.08.2026

### Eine beschädigte param.json wird erkannt und repariert

- Bisher reichte es, dass sich die Datei überhaupt lesen ließ. Alles andere merkte man erst an der Konsole: „Missing/invalid param.json" – und niemand wusste, woran es lag.
- Jetzt wird sie inhaltlich geprüft. Auffällig sind zum Beispiel eine Versionsnummer, die als Zahl statt als Text gespeichert ist, eine Content-ID, die zu einer anderen Titel-ID gehört, ein fehlender Sprachblock oder ein unsichtbares Zeichen am Dateianfang.
- Wird etwas gefunden, bietet das Programm an, es zu **reparieren**. Ihre vorhandenen Angaben bleiben dabei erhalten – Titel, Altersfreigaben und Versionsstände werden nicht überschrieben. Die bisherige Fassung liegt danach als `param.json.alt` daneben.
- Das gilt beim Erstellen jedes Formats **und im Validator (Aufgabe 8)**: Dort wird die Datei mitgeprüft und die Reparatur gleich angeboten, statt den Befund nur zu melden.
- Für Skripte gibt es zwei neue Schalter: `--param-json-reparieren` repariert ohne Rückfrage, `--param-json-online` erlaubt das Nachschlagen von Titel und Content-ID im Netz. Beide sind aus, solange man sie nicht setzt.

---

## v1.8.50 – 18.08.2026

### Die Anwendung läuft jetzt auch auf dem Mac

- Neben der Windows-EXE und der Linux-Programmdatei entsteht auf einem Mac ein richtiges Programmbündel: **PS5 Dump & Image Converter.app**. Es hat ein Symbol im Dock, einen eigenen Namen in der Menüleiste und lässt sich wie jedes andere Mac-Programm starten.
- Erstellt wird es mit `./Build_macOS.sh`, in den Programme-Ordner gelegt mit `./Install_macOS.sh` – samt Eintrag im Launchpad. Ein Passwort ist dafür nicht nötig.
- Das Fenster wird in voller Bildschärfe gezeichnet und folgt dem dunklen Erscheinungsbild des Systems. Fehlt *Segoe UI*, wählt das Programm selbst die passendste Schrift Ihres Macs.
- Es gelten dieselben Einschränkungen wie unter Linux: `.ffpkg` lesen und erstellen sowie die Ersatzwege über OSFMount bleiben Windows vorbehalten. Alle übrigen Aufgaben stehen vollständig zur Verfügung, und das Programm sagt jetzt ausdrücklich „macOS“, wenn ein Weg dort nicht offensteht.
- Das Handbuch hat dafür ein neues Kapitel bekommen: **19 – Die Anwendung auf dem Mac**.

---

## v1.8.49 – 18.08.2026

### Nur Bibliotheken kommen in den fakelib-Ordner

- Bisher wurde der komplette mitgelieferte Ordner in das Spiel kopiert. Beim Satz für Firmware 7 war darin auch eine `ps5-backpork.elf` – 116 KB, der Payload des Werkzeugs, aus dem die Sätze stammen. Eine Bibliothek ist das nicht.
- ShadowMount+ hängt den Ordner nach `common/lib`, wo Bibliotheken **nach Namen** geladen werden, wenn ein Spiel sie anfordert. Nach dieser Datei fragt kein Spiel; sie war nur Ballast im Spielverzeichnis.
- Übernommen werden jetzt `.sprx` und `.prx`. Die leere Markierungsdatei (`FW7` und so weiter) bleibt erhalten – sie kostet nichts und verrät später, welcher Satz im Ordner liegt.
- Im Protokoll steht, was übersprungen wurde. Nur der Satz für Firmware 7 ist betroffen; in den Sätzen für 4, 5 und 6 gibt es die Datei gar nicht.
- Bereits erzeugte Backups bleiben unverändert. Die Datei darin richtet keinen Schaden an.

---

## v1.8.48 – 17.08.2026

### Man sieht jetzt, ob ein Backup zurückportiert ist

- Im Fenster **Spiel Info** steht eine neue Zeile **SDK (eboot.bin)**. Ist ein Backup zurückportiert, steht dort zum Beispiel `7.00 (zurückportiert – param.json nennt 9.00)`.
- Vorher war das nicht zu sehen: Ein Backport ändert nur die Kopfdaten von `eboot.bin` und der `.prx`-Dateien, nicht die `param.json` – und genau die wurde angezeigt.
- Auch die Meldung der Konsole hilft dabei nicht. ShadowMount+ meldet „Spiel backportiert", sobald ein Bibliotheksordner eingehängt wurde. Ein AMPR-EMU-Paket löst dieselbe Meldung aus, obwohl es nicht zurückportiert ist.

### REQUIRED FW zeigte oft den falschen Wert

- Bei **13 von 32** geprüften Spielen stand dort eine falsche Firmware, zum Beispiel `01.00.10.00` statt `10.01.00.00`.
- Betroffen war jedes Spiel mit zweistelliger Hauptversion (10, 11, 12).

### Ersatzbibliotheken: `fakelib` oder `fakelib2` wählbar

- Die Wahl steht im Fenster **BACKPORT** und im **AMPR EMU Manager**. Beide teilen dieselbe Einstellung: Wer an einer Stelle umstellt, stellt die andere mit um.
- Das muss so sein, weil ShadowMount+ nur **einen** der beiden Ordner einhängt und `fakelib2` bevorzugt. Zwei verschiedene Ordner hätten bedeutet, dass einer wirkungslos bleibt – ohne jede Meldung.
- Liegen nach einem Lauf beide Ordner vor, warnt das Programm und nennt den, der wirkt.
- Voreingestellt bleibt `fakelib`; es ändert sich also nichts von allein.

### Fortschrittsanzeige beim `.ffpkg`-Bau

- Der Balken stand zuletzt **49 von 87 Sekunden** unverändert bei 98 %, während im Hintergrund noch geprüft, kopiert und geprüft wurde.
- Jetzt läuft er durch: Der längste Stillstand liegt bei 10 Sekunden, und der Balken zeigt dreimal so viele Zwischenschritte.

### Aussehen und Sprache

- Neue Vorgabe-Hintergrundbilder (`bg_19_ray-burst`, `sidebar_20_glass-panels`). Eine eigene Wahl bleibt erhalten, „kein Bild" bleibt „kein Bild".
- Beim Wechsel des Designs werden jetzt auch die Knöpfe der Titelleiste, die Aufgabenknöpfe, die beiden Knöpfe unten in der Seitenleiste und die Klappmenüs mit umgefärbt. Im hellen Design war ein Knopf vorher praktisch unlesbar.
- Das Rechtsklick-Menü ist übersetzt – es war fest deutsch.
- Am Feld **WORKER-THREADS** erklärt ein Hinweis, was die gewählte Zahl bewirkt.

---

## v1.8.47 – 17.08.2026

### Die Kompressionsstufe wirkt endlich

- Die Auswahl **KOMPRESSION (PFS)** mit den Stufen 1, 3, 6 und 9 blieb ohne jede Wirkung. Gepackt wurde immer mit einer fest im Programm hinterlegten Stufe – 9 bei Aufgabe 1, 8 bei Aufgabe 3 und 6, 7 bei Aufgabe 4. Alle vier Stufen erzeugten dieselbe Datei.
- Besonders irreführend war die **Größenvorhersage** neben dem Quellfeld: Sie rechnete sehr wohl mit der gewählten Stufe, nur mit dem falschen Verfahren (zstd statt zlib). Die angekündigte Zielgröße änderte sich also beim Umstellen, die fertige Datei nie – genau dieser Widerspruch fällt beim Benutzen auf.
- Beides ist behoben. Die gewählte Stufe geht jetzt an die Engine, und die Vorhersage rechnet mit demselben Verfahren, das auch packt. An einem Testlauf gemessen: Stufe 1 ergibt 1.769.472 Bytes, Stufe 9 ergibt 1.310.720 Bytes – vorher waren es in allen vier Stellungen 1.310.720 Bytes.
- Der Startwert stand auf einer Stufe (7), die das Auswahlfeld gar nicht anbietet; er steht jetzt auf 6 – „Ausgewogen“, wie im Feld voreingestellt.
- Die angezeigte Zielgröße rechnet sich beim Umstellen der Stufe **sofort neu**. Bisher entstand sie nur beim Wechsel der Quelle; wer allein die Stufe änderte, sah weiterhin den alten Wert stehen – auch das ließ die Auswahl wirkungslos aussehen.

### Die Anwendung läuft jetzt auch unter Linux

- Es gibt eine **Linux-Fassung**: eine einzelne, eigenständige Programmdatei, gebaut mit `./Build_Linux.sh`. `./Install_Linux.sh` legt sie mit Symbol ins Anwendungsmenü, `--entfernen` nimmt das zurück.
- Die Oberfläche, alle acht Aufgaben in ihren nativen Wegen, der Kommandozeilenmodus und die Werkzeugfenster arbeiten dort wie gewohnt. **Root-Rechte braucht der normale Betrieb nicht** – unter Windows fragt das Programm beim Start danach, unter Linux startet es als normaler Benutzer.
- **Was unter Linux nicht geht:** `.ffpkg` lesen und bauen sowie die OSFMount-Ersatzwege. Diese hängen an UFS2Tool, dem Dokan-Treiber und OSFMount – reiner Windows-Software. Wählt man eine solche Aufgabe, sagt das Programm das jetzt klar, statt fehlende Administratorrechte zu melden. Die nativen MkPFS- und exFAT-Wege sind vollständig vorhanden.
- Die Einstellungen liegen unter Linux in `~/.config/PS5ImageConverterPro/`. Handbuch, Lizenzdateien und Zielordner öffnen über die Werkzeuge der Arbeitsumgebung; „im Dateimanager zeigen“ funktioniert mit Nautilus, Dolphin, Nemo und Thunar. Auch das Herunterfahren nach erfolgreichem Abschluss funktioniert dort – bisher meldete es „nur unter Windows unterstützt“.
- Die Oberfläche ist auf *Segoe UI* ausgelegt. Fehlt sie, sucht das Programm die beste vorhandene Schrift des Systems aus, statt auf eine beliebige Ersatzschrift zu fallen.

### Auch unter Windows behoben

- Beim Backport wurde `libc.prx` nicht mehr erkannt, sobald der Pfad aus PS5-Metadaten oder einer FTP-Liste stammte statt aus dem Dateisystem. Der Patch wurde dann stillschweigend übersprungen. Dateinamen werden jetzt an beiden Pfadtrennzeichen erkannt.

---

## v1.8.46 – 17.08.2026

### Protokollfeld: jetzt an der richtigen Stelle behoben

- Trotz v1.8.44 und v1.8.45 klebten weiterhin Meldungen und Fortschrittsbalken aneinander, zum Beispiel `>>> Schritt 2 / 2: inneres PFS -> komprimierter Aussencontainer...[####] 100% compress`.
- Beide Vorversionen hatten das **Einlesen** der Engine-Ausgabe verbessert. Der Fehler saß aber in der **Anzeige**: Wenn ein Fortschrittsbalken fortgeschrieben wird, muss die alte Zeile weg – und dabei verlor die Zeile darüber ihren Zeilenumbruch. Das Feld endete offen, und was danach kam, landete hinten an dieser Zeile.
- **Dabei gingen Meldungen verloren.** Eine so verklebte Zeile enthält einen Fortschrittsbalken und wurde beim nächsten Balken komplett gelöscht – mitsamt der Meldung darin. Bei einem gemessenen Lauf fehlten dadurch **72 Zeilen**, unter anderem der komplette Parameterblock mit Quell- und Zielpfad. Genau deshalb sah dieser Block im Feld immer abgeschnitten aus.
- Beides ist behoben: Vor jedem Einschub wird eine offene Zeile geschlossen. Fortschrittsbalken schreiben sich weiter fort wie bisher, und beim Wechsel des Arbeitsschritts bleibt der abgeschlossene Balken als Beleg stehen.

---

## v1.8.45 – 17.08.2026

### Protokollfeld: die zweite Stelle

- Nach v1.8.44 klebten bei **einigen** Aufgaben weiterhin Text und Fortschrittsbalken in einer Zeile, etwa `==========[####] 97% extract @ 96.35 MB/s`.
- Der Grund: Es gibt zwei Wege, auf denen Ausgaben ins Protokollfeld kommen. v1.8.44 reparierte den einen; Engines, die als eigener Prozess laufen (für `.exfat` und `.ffpkg`), liefern ihre Ausgabe dagegen **am Stück** – und dort wurde der Wagenrücklauf ersatzlos entfernt, statt als Zeilenwechsel zu gelten.
- Auch dieser Weg fasst jetzt Fortschrittszeilen zusammen. Damit ist das Feld bei allen Aufgaben ruhig.

---

## v1.8.44 – 17.08.2026

### Protokollfeld: Text und Fortschrittsbalken klebten aneinander

- Während einer Aufgabe standen im Protokollfeld Zeilen wie `Writing PFS image to E:\…\pfs_image.dat...[####------] 72% write @ 106 MB/s` – Meldung und Fortschrittsbalken in **einer** Zeile.
- Als Folge davon **stapelten sich die Balken**: Weil eine solche Zeile nicht als Fortschrittszeile erkannt wurde, hängte das Programm die nächste an, statt die vorige zu ersetzen. Das Feld lief mit fast gleichen Zeilen voll, und beim Rollen blieb oben eine angeschnittene Zeile stehen.
- Beides ist behoben. Jetzt steht **je Arbeitsschritt eine Zeile**, die sich fortschreibt; wechselt der Schritt (lesen → schreiben → komprimieren), bleibt die abgeschlossene Zeile als Beleg stehen.

---

## v1.8.43 – 17.08.2026

### PS5-Verbindung an einer Stelle

- In den **EINSTELLUNGEN** gibt es den neuen Abschnitt **PS5-Verbindung**: IP-Adresse, FTP-Port und KLOG-Port. Gespeichert wird beim Druck auf **Speichern**.
- Alle Fenster, die eine Verbindung brauchen – FTP-Übertragung, **KLOG**, **ShadowMount+/MicroMount**, AMPR Picker und **JS LOADER** – schlagen diese Werte vor. Bisher hielt jedes Fenster seine eigene Adresse, und beim JS Loader stand sie sogar fest im Programm. Wer die Konsole umzieht, musste sie an vier Stellen nachtragen.
- Ein Fenster, in dem Sie bewusst etwas anderes eintragen, behält seine eigene Angabe.
- **Stimmt ein Port nicht, findet das Programm ihn selbst.** Antwortet der eingetragene nicht, werden die bekannten durchprobiert (FTP: 2121, 1337, 21, 2120) und der wirksame übernommen und gemerkt.
- Ein Knopf **Verbindung testen** sagt sofort, ob die Konsole antwortet – und über welchen Port.

### KLOG hilft weiter, statt stumm zu bleiben

- Der Knopf **KLOG** prüft jetzt zuerst, ob auf der Konsole überhaupt etwas zuhört. Bisher öffnete sich nur ein Fenster, das keine Verbindung bekam.
- Läuft klogsrv noch nicht, antwortet aber der Payload-Loader, wird angeboten, den mitgelieferten Payload direkt zu senden.
- Antwortet auch der nicht, kann der Payload **per FTP auf einen an der PS5 angeschlossenen USB-Datenträger** übertragen werden. Gibt es dort einen Ordner `ps5_autoloader`, wird die Datei dorthin gelegt und in `autoload.txt` eingetragen – unter dem letzten Eintrag zuerst eine Pause, darunter der Dateiname. Gibt es den Ordner nicht, wird das Wurzelverzeichnis angeboten; das passt für den Payload Manager.

### Übersichtlichere Bibliothek

- Die Liste hat endlich **Rollbalken** – vorher war nicht zu sehen, dass es weitergeht.
- **Titel und Pfade werden nicht mehr abgeschnitten**; die Spalten sind breiter und wachsen mit dem Fenster.
- Ein Klick auf eine Spaltenüberschrift **sortiert**, ein zweiter dreht die Richtung um.
- Abwechselnd eingefärbte Zeilen machen es leichter, eine Zeile über alle Spalten zu verfolgen.
- In einem kleinen Fenster fehlten die Knöpfe am unteren Rand ganz – sie sind jetzt immer da.

### Ruhigeres Protokollfeld, ehrlichere Fortschrittsanzeige

- Der Fortschrittsbalken der Engine füllte das Protokollfeld mit hunderten fast gleichen Zeilen, und beim Rollen blieb oben eine angeschnittene Zeile stehen. Jetzt steht dort **eine** Zeile, die sich fortschreibt.
- Die Fortschrittsanzeige **blieb mitten in Aufgabe 1 mehrere Sekunden stehen** (bei einer kleinen Quelle 8–11 s, bei großen entsprechend länger), obwohl gearbeitet wurde. Sie läuft jetzt durch.
- Die Erklärtexte zu den Hintergrundbildern in den EINSTELLUNGEN sind deutlich kürzer.

---

## v1.8.42 – 16.08.2026

### Knopf BENUTZERHANDBUCH

- In der Titelleiste steht links neben **EN** ein neuer Knopf **BENUTZERHANDBUCH**. Ein Druck öffnet die Anleitung in Ihrem Browser.
- Das Handbuch liegt dem Programm bei – eine Internetverbindung braucht es dafür nicht.

### Fehlermeldungen, die stumm blieben

- Schlug ein **BACKPORT** fehl, blieb die Statuszeile auf dem alten Stand stehen, statt den Grund zu nennen. Sie zeigt ihn jetzt wieder.
- Dasselbe galt im Fenster **ShadowMount+/MicroMount** beim Laden und Schreiben der Konfiguration und beim Holen des Debug-Logs: Ging etwas schief, war das an der Oberfläche nicht zu sehen.

### Kleinere Verbesserung

- Im Fenster **EINSTELLUNGEN** lief der Hinweistext unten halb unter die Knöpfe *Speichern* und *Schließen* und war abgeschnitten. Er steht jetzt in einer eigenen Zeile darüber und bricht passend zur Fensterbreite um.

---

## v1.8.41 – 16.08.2026

### Zehn weitere Hintergrundbilder für den Hauptbereich

- Die Klappliste **Hintergrundbild** in den EINSTELLUNGEN bietet jetzt **zwanzig** Bilder statt zehn.
- Die neuen Bilder zeigen dieselben Motive wie die hohen Bilder der Seitenleiste: Polarlicht, Lichtstrahlen, Bokeh, Sternenfeld, Höhenlinien, Wellenringe, Fluchtpunktraster, Punktraster, ein Gitternetz mit Lichtschein und warme Bänder. Damit lassen sich Hauptbereich und Seitenleiste erstmals auf dasselbe Motiv einstellen.
- Sie sind so dunkel gehalten wie die bisherigen, damit Karten, Beschriftungen und Statuszeile davor lesbar bleiben.

---

## v1.8.40 – 16.08.2026

### FILEZILLA startet immer Ihr FileZilla

- Der Knopf **FILEZILLA** öffnete bisher ersatzweise ein eingebautes FTP-Fenster, wenn FileZilla nicht gefunden wurde. Dieses Fenster ist entfallen – der Knopf startet ausschließlich Ihre eigene Installation.
- **FileZilla wird jetzt auch an ungewöhnlichen Orten gefunden.** Bisher half nur eine feste Liste bekannter Pfade. Gesucht wird nun in jedem Ordner, dessen Name „FileZilla“ enthält – in den Programmordnern, unter `AppData` und direkt auf jedem festen Laufwerk. Damit werden auch `C:\FileZilla`, eigene Ordnernamen wie `FileZilla3_x64` und portable Ablagen erkannt.
- **Gesucht wird nur einmal.** Der Pfad wird nach dem Start gemerkt; beim nächsten Programmstart öffnet der Knopf FileZilla sofort. Passt der gemerkte Pfad nicht mehr, beginnt die Suche von selbst neu.
- Dasselbe galt für **OSFMount**: Auch dort wurde bei jedem Einhängen eines Abbilds neu gesucht. Der Pfad wird jetzt ebenfalls gemerkt.

### Hintergrundbilder getrennt wählbar

- Die **Sidebar** hat jetzt eine eigene Klappliste mit den mitgelieferten Bildern – wie der Hauptbereich. Vorher ließ sich dort nur ein eigenes Bild von der Festplatte wählen.
- Beide Listen zeigen nur, was in den jeweiligen Bereich passt: die breiten Bilder beim Hauptbereich, die hohen bei der Seitenleiste. Unterschieden wird am Bildformat, ein eigenes Bild landet also automatisch richtig.
- Das **Sidebar-Bild tritt jetzt weiter zurück** (50 statt 85 % Deckkraft). Im Hauptbereich verdecken Karten den größten Teil des Bildes – in der Seitenleiste steht es frei und wirkte dadurch deutlich kräftiger. Jetzt sind beide Bereiche gleich dezent.
- **Die Statuszeile flackerte** während einer laufenden Aufgabe. Sie bekommt – wie alle Beschriftungen auf dem Hintergrundbild – einen passenden Bildausschnitt hinterlegt; um dessen Größe zu bestimmen, wurde die Beschriftung kurz ohne diesen Ausschnitt gezeichnet. Bei jedem Fortschrittswert erneut, also mehrmals je Sekunde. Gemessen wird jetzt unsichtbar im Hintergrund.
- Der Einstellungen-Dialog hat einen Knopf **Speichern**. Änderungen wirken weiterhin sofort; der Knopf sichert den Stand und schließt das Fenster, damit man es nicht im Zweifel verlässt, ob etwas übernommen wurde.

### Danksagung vervollständigt

- Im Fenster **CREDITS** und in den beiliegenden Dokumenten sind jetzt alle 24 mitgelieferten Payloads namentlich aufgeführt, mit ihren Autoren, soweit diese aus den Dateien selbst hervorgehen. Ergänzt wurden außerdem die Grundlagen der BACKPORT-Funktion, der PlayGo-Stub, die genutzte Onlinequelle und das Forum psxtools.de.

---

## v1.8.39 – 16.08.2026

### Ruhiger Programmstart

- Beim Start blitzte das Fenster kurz **weiß** auf, danach schoben sich die Bedienelemente sichtbar an ihren Platz. Das Fenster erscheint jetzt erst, wenn es fertig aufgebaut ist. Dasselbe galt für alle Werkzeugfenster – auch sie öffnen sich nun sofort dunkel.
- In der Seitenleiste stand der **Spielname zeitweise über dem Cover** statt darunter, das Bild verschwand für einen Moment ganz und wanderte danach mehrfach. Cover und Name sitzen jetzt von Anfang an fest; nur der Name wird nachgetragen, sobald er bekannt ist.
- Der Spielname unter dem Cover ist **etwas größer**, und der Block aus Bild und Name sitzt ein Stück tiefer in der Seitenleiste.
- Der Startbildschirm hat **abgerundete Ecken**.
- Das Fenster, das beim Nachinstallieren von Dokan 2 erscheint, stand in hellen Systemfarben mit kaum lesbarer Schrift. Es passt sich jetzt dem Design an.

---

## v1.8.38 – 16.08.2026

### Hochgeladene Spiele starteten nicht mehr — behoben

Wer seit dem 15.08. ein Spiel mit diesem Programm auf die Konsole geladen hat, bekam beim Start **CE-107750-0** und sonst keinen Hinweis. Die Ursache lag nicht am Spiel und nicht an der Konvertierung, sondern am Übertragungsweg.

**Was passiert war:** Für mehr Tempo wurde bevorzugt der Payload **zftpd** (Port 2120) genutzt. Der legt jede hochgeladene Datei jedoch ohne Ausführungsrecht ab (Rechte `0666`). Die PS5 startet nichts, was nicht ausführbar ist – und nennt als Grund nur diesen Fehlercode. Der zuvor verwendete **ftpsrv** (Port 2121) legt Dateien mit `0777` ab; damit startet alles wie gewohnt.

An der Konsole nachgemessen, dieselbe Datei im selben Ordner:

| Payload | Port | Rechte danach |
| --- | --- | --- |
| ftpsrv 1.15-ng | 2121 | `0777` ✅ |
| zftpd 1.5.0 | 2120 | `0666` ❌ |

**Was sich ändert:**

- Das Programm verwendet wieder **ftpsrv auf Port 2121**. Läuft er nicht, wird wie gewohnt angeboten, den mitgelieferten Payload zu senden.
- zftpd wird nicht mehr angeboten und steht in der Suchreihenfolge ganz hinten – falls jemand ausschließlich zftpd laufen hat, kommt wenigstens eine Verbindung zustande.
- **Neu: Nach jedem Upload prüft das Programm die Rechte** und warnt im Protokoll, wenn eine Datei nicht ausführbar ist. Vorher blieb dieser Fehler stumm, bis das Spiel nicht anlief.

> **Wenn ein Spiel bei Ihnen nicht startet:** Laden Sie es mit dieser Version noch einmal hoch. Über zftpd übertragene Ordner bleiben unbrauchbar, solange die Rechte nicht stimmen – nachträglich lassen sie sich über zftpd auch nicht reparieren.

---

## v1.8.37 – 16.08.2026

### Beschnittene Knöpfe in vier Fenstern

Im neuen **BACKPORT**-Fenster waren die drei Knöpfe am unteren Rand leer – man sah nur graue Rechtecke – und das Feld für die Zielfirmware zeigte nichts an. Die Prüfung aller Fenster förderte dieselbe Ursache an drei weiteren Stellen zutage.

**Was dahintersteckte:** Wenn eine Liste, die sich über den ganzen freien Platz ausdehnt, vor der darunterliegenden Knopfleiste angelegt wird, nimmt sie sich den Platz zuerst. Für die Knöpfe bleibt dann nur der Rest – gemessen 24 statt 51 Pixel Höhe, zu wenig für die Beschriftung. Die Reihenfolge ist jetzt umgedreht: erst die feste Knopfleiste, dann die Liste in den verbleibenden Raum.

| Fenster | Was zu sehen war |
| --- | --- |
| **PKG-MERGER** | **Gar keine Knöpfe** – weder „Zusammenführen" noch „Schließen" |
| **BACKPORT** | Drei Knöpfe ohne Beschriftung, Firmware-Auswahl leer |
| **DOWNLOADS** | Fünf Knöpfe der unteren Reihe beschnitten |
| **ShadowMount+ / MicroMount** | Knöpfe der Listenzeile beschnitten, „Auf PS5 schreiben…" seitlich gekappt |
| **JS Loader** | „Konsole leeren" auf 8 Pixel Breite geschrumpft, praktisch unsichtbar |

Der **PKG-Merger** war dabei am stärksten betroffen: Dort blieb von der Knopfleiste nichts übrig, das Fenster ließ sich also nur über das Kreuz in der Titelzeile schließen und die Zusammenführung gar nicht auslösen. Aufgefallen ist das erst beim zweiten Durchgang – im ersten öffnete sich das Fenster nicht, weil es einen Ordner mit geteilten `.pkg`-Dateien voraussetzt.

**Dazu im Einzelnen:**

- Die **Firmware-Auswahl im Backport-Fenster** blieb leer, weil der interne Wert nach dem Öffnen des Fensters verworfen wurde. Dass trotzdem „Firmware 7.00" in der Statuszeile stand, war Zufall – ohne Auswahl griff das Programm auf den letzten Listeneintrag zurück, und das ist zufällig ebenfalls 7.00. Jetzt zeigt das Feld seinen Wert an, und ohne Auswahl gilt ausdrücklich die Voreinstellung.
- Im **JS Loader** stehen die Aktionsknöpfe jetzt in zwei Zeilen. Alle fünf nebeneinander brauchten mehr Breite, als das Fenster hat.
- Bei **ShadowMount+ und MicroMount** ist das Fenster etwas breiter; die Tabelle zeigt 12 statt 16 Zeilen auf einmal und lässt sich wie bisher scrollen.
- Im Download-Fenster heißt der Knopf jetzt kurz **Umsortieren**; was er tut, steht im Hinweis beim Darüberfahren.

Ein neuer Test öffnet die betroffenen Fenster und misst jeden Knopf aus, damit diese Fehlerklasse nicht unbemerkt zurückkehrt.

---

## v1.8.36 – 16.08.2026

### Titel und Content-ID bei defekter param.json

Fehlt `sce_sys/param.json` oder ist sie beschädigt, bietet das Programm seit jeher an, eine Ersatzdatei anzulegen. Seit v1.8.33 stammt die Titel-ID dafür zuverlässig aus `sce_sys/nptitle.dat`. **Titel und Content-ID standen dagegen in keiner einzigen lokalen Datei** – auch nicht in der `eboot.bin` (33 MB vollständig durchsucht) oder in `npbind.dat`. Die Ersatzdatei blieb an diesen beiden Stellen leer.

Beide lassen sich jetzt zur Titel-ID nachschlagen – auf derselben Seite, von der auch die Update-Liste im Fenster *Spiel-Info* kommt.

**Sie werden vorher gefragt.** Es ist eine eigene Ja/Nein-Rückfrage, getrennt von der Frage, ob überhaupt eine Ersatzdatei entstehen soll. Sie steht auf **Nein** voreingestellt und nennt ausdrücklich, was gesendet wird: die Titel-ID, sonst nichts.

**Ohne Nachschlag geht nichts verloren.** Sagen Sie Nein, gibt es kein Internet oder antwortet die Seite nicht, entsteht die Ersatzdatei genau wie bisher – nur mit der Titel-ID. Die Reparatur scheitert nie am Nachschlag.

An acht Backups nachgemessen: Die **Content-ID stimmte 8 von 8 Mal exakt**, der **Titel 7 von 8 Mal**. Die eine Abweichung ist eine Umbenennung zwischen Regionen (lokal „Instant Sports Plus", online „Instant Sports Paradise") – die Content-ID stimmte auch dort.

### Behobener Fehler

- **Im Fenster Spiel-Info stand die Titel-ID vor dem Titel.** Die Patch-Seite stellt sie seit einiger Zeit voran, sodass dort `PPSA19015: Arcade Game Zone` erschien statt `Arcade Game Zone`. Betraf nur den Fall, dass der Titel online geholt wurde.

---

## v1.8.35 – 16.08.2026

### BACKPORT – Spiele auf ältere Firmware herabsetzen

Ein PS5-Spiel merkt sich, mit welchem Entwicklungspaket (SDK) es gebaut wurde, und startet nur auf Firmware, die mindestens so neu ist. Verlangt ein Spiel 9.00, während die Konsole auf 4.50 steht, passiert beim Start nichts. Der neue Eintrag **BACKPORT** im Menü **WEITERE TOOLS** setzt diese Angabe herab.

**So läuft es ab:** Ordner wählen, Zielfirmware einstellen, auf *Backport starten* klicken. Das Programm geht jede ausführbare Datei durch – `eboot.bin`, `.prx` und `.sprx` –, entpackt sie, setzt die SDK-Angabe im Modulkopf herunter, signiert sie neu und legt zum Schluss die zur Zielfirmware passenden Ersatzbibliotheken in einen Ordner `fakelib` daneben. Zur Auswahl stehen die Firmware-Stände **4.00, 5.00, 6.00 und 7.00**; für jeden liegt ein eigener Bibliothekssatz bei.

**Was dabei geschützt ist:**

- **Sicherung zuerst.** Auf Wunsch (standardmäßig an) entsteht neben dem Spielordner eine vollständige Kopie mit Zeitstempel, bevor irgendetwas angefasst wird.
- **Alles oder nichts pro Datei.** Gearbeitet wird ausschließlich im Arbeitsspeicher. Eine Datei wird erst ersetzt, wenn Entpacken, Patchen *und* Neusignieren gelungen sind – und dann in einem Zug. Bricht ein Schritt ab, bleibt das Original unverändert.
- **Nur herabsetzen.** Dateien, die schon niedrig genug sind, bleiben unangetastet und werden als übersprungen ausgewiesen. Angehoben wird nie.
- **Nichts wird doppelt gepatcht.** Der Ordner `fakelib` bleibt außen vor – die Bibliotheken darin passen bereits.

**Vor dem Start sehen, was passieren würde:** Der Knopf **Nur prüfen** liest jede Datei und zeigt in der Liste ihr aktuelles SDK sowie das, was mit ihr geschähe – ohne etwas zu ändern. Beim Öffnen des Fensters läuft diese Prüfung automatisch.

**Zusätzlich abschaltbar:** Ein Ankreuzfeld aktiviert einen zusätzlichen Zeichenkettenpatch in `libc.prx`, der bei manchen Spielen für 6.xx nötig ist. Er ist als experimentell gekennzeichnet und standardmäßig aus.

> **Bestätigt am 16.08.2026:** Ein so behandeltes Spiel (Terminator 2D, von 10.00 auf 7.00 herabgesetzt) startet und läuft auf einer echten PS5 – mit den Ersatzbibliotheken erscheint dabei die Einblendung „Spiel backportiert“.
>
> **Bitte trotzdem beachten:** Das Ergebnis wird neu signiert, aber nicht *echt* signiert – es läuft nur auf einer bereits gejailbreakten Konsole. Ob ein bestimmtes Spiel nach dem Backport tatsächlich startet, hängt vom Spiel ab; manche verlangen Funktionen, die es auf der älteren Firmware schlicht nicht gibt. Deshalb: immer mit Sicherung arbeiten.

Alles läuft ohne Fremdwerkzeug und ohne zusätzliche Laufzeitumgebung – die Verfahren zum Entpacken und Signieren sind im Programm selbst nachgebaut.

---

## v1.8.34 – 16.08.2026

### Updates und Patches wirklich herunterladen

Bisher führte der Knopf **Download** im Fenster **Spiel-Info – Updates & Patches** nur auf eine Internetseite. Von dort musste die Datei von Hand geholt, selbst einsortiert und im Blick behalten werden. Das übernimmt jetzt das Programm.

- **Neuer Eintrag DOWNLOADS** im Menü **WEITERE TOOLS**. Dort stehen laufende und bereits vorhandene Downloads in einer Liste: Dateiname, Title-ID, Art, Größe, Fortschritt und Status.
- **Getrennte Ordner, automatisch einsortiert.** Die neueste Version eines Spiels gilt als Update und landet in **PS5 Spiele Updates**, jede ältere Fassung als Patch in **Patches**. Beide Ordner entstehen unterhalb des von dir gewählten Speicherorts. Liegt eine Datei im falschen Ordner, verschiebt sie der Knopf **Als Update/Patch umsortieren**.
- **Speicherort frei wählbar.** Beim ersten Download wird gefragt, auf welchem Datenträger die Pakete liegen sollen. Ändern lässt sich das jederzeit in den **Einstellungen** unter *Speicherort für Downloads* oder direkt im Download-Fenster.
- **Abbrechen und fortsetzen.** Ein laufender Download lässt sich anhalten; **Erneut versuchen** setzt genau dort fort, wo er stehen geblieben ist, statt von vorn zu beginnen. Auch ein Programmabsturz kostet den Fortschritt nicht.
- **Halbe Dateien sehen nie fertig aus.** Geladen wird in eine Datei mit der Endung `.teil`; erst wenn die Größe stimmt, bekommt sie ihren richtigen Namen.
- **Vorhandene einlesen** durchsucht beide Ordner und zeigt, was schon da ist – nützlich nach einem Neustart oder auf einem neu angeschlossenen Datenträger.

**Ein Schritt bleibt von Hand:** Die eigentliche Download-Adresse entsteht erst, wenn auf der Patch-Seite im Browser auf **DETAILS** geklickt wird, und dieser Klick ist dort absichtlich durch eine Sicherheitsabfrage geschützt. Das Programm umgeht diesen Schutz nicht. Der Ablauf ist deshalb: Auf **Download** klicken – die Seite öffnet sich, das Download-Fenster kommt nach vorn. Auf der Seite die Sicherheitsabfrage bestätigen, mit der rechten Maustaste auf **Download Piece PKG** klicken und *Link kopieren* wählen. Zurück im Download-Fenster genügt dann **Aus Zwischenablage** – alles Weitere läuft von allein. Mehrere Adressen dürfen auf einmal eingefügt werden.

---

## v1.8.33 – 15.08.2026

Ein zweiter Durchgang mit sechs anderen Backups (22 Konvertierungen über alle acht Aufgaben) hat weitere Fehler zutage gefördert. Sie sind hier behoben.

### Behobene Fehler

- **Beim Entpacken einer `.ffpkg` fehlte hinterher eine Datei.** Aus einem Paket mit 196 Dateien kamen 195 heraus; verloren ging `sce_sys/about/right.sprx` – eine Datei, die in jedem geprüften Backup vorkommt. Gemeldet wurde lediglich „robocopy fehlgeschlagen (rc=9)", ohne zu sagen, was fehlt. Das Ergebnis wird jetzt Datei für Datei gegen das Abbild geprüft, Fehlendes einzeln nachgeholt, und falls doch etwas übrig bleibt, nennt die Meldung die betroffenen Dateien beim Namen.
- **Quelldateien mit Sonderzeichen im Namen brachen den Packlauf ab.** `Matchbox™ Driving Adventures (01.000.001).exfat` endete mit einer Fehlermeldung über „non-ASCII characters", weil ein Containerverzeichnis solche Zeichen nicht speichern kann. Jetzt werden nur die betroffenen Zeichen ersetzt (`™` → `(TM)`, `–` → `-`), der übrige Name samt Versionsklammer bleibt erhalten.
- **Die Sammelkonvertierung verweigerte den Start wegen einer einzigen Quelle.** Lag in einer gemischten Auswahl eine Datei schon im Zielformat vor, wurde der gesamte Auftrag abgelehnt. Solche Quellen werden jetzt übersprungen und im Protokoll benannt; abgelehnt wird nur noch, wenn es überhaupt nichts zu tun gibt.
- **`.ffpfs` ließ sich nicht nachträglich komprimieren.** Der Weg `.ffpfs` → `.ffpfsc` (und umgekehrt) galt als „Quelle und Zielformat sind identisch", obwohl beide Formate sich genau darin unterscheiden.
- **Ein gewähltes Hintergrundbild war nach jedem Neustart weg.** Wurde eines der mitgelieferten Bilder ausgewählt, merkte sich das Programm einen Pfad, den es nach dem Beenden nicht mehr gibt – die Einstellung fiel still auf das Standardbild zurück. Bestehende Einstellungen werden beim nächsten Start automatisch repariert.
- **Geteilte `.pkg`-Dateien mit Punkt im Namen wurden übersehen.** Ein Satz wie `Spiel (01.003.000)_0.pkg` galt als „entspricht nicht dem Split-Namensschema" und tauchte im PKG-Merger gar nicht erst auf.
- **Arbeitsordner blieben liegen.** Nach jedem Lauf über die Kommandozeile blieb ein Ordner mit rund einem halben Megabyte im Temp-Verzeichnis zurück. Er wird jetzt am Ende entfernt, und Reste älterer Läufe werden beim Start mit aufgeräumt.

### Spiel-Info bleibt während einer Konvertierung nicht mehr leer

- Solange eine Aufgabe lief, holte das Programm keine Metadaten zur gewählten Quelle – aus gutem Grund, denn das Lesen eines mehrere Gigabyte großen Containers würde der laufenden Arbeit Platte und Rechenzeit wegnehmen. Nur sagte es das nicht: Das Fenster **Spiel-Info – Updates & Patches** blieb leer, und schlimmer, es zeigte teils noch Titel und Cover der **vorher** gewählten Quelle. Jetzt steht dort „Wird nach Abschluss der laufenden Aufgabe geladen", die alten Werte verschwinden, und sobald die Aufgabe fertig ist, werden Metadaten, Updates und Downloads automatisch nachgeladen.

### Bessere Title-ID bei defekter param.json

- Fehlt `sce_sys/param.json` oder ist sie beschädigt, bietet das Programm seit jeher an, eine Ersatzdatei anzulegen. Die dafür nötige Titel-ID wurde bisher ausschließlich aus dem **Ordnernamen** geraten – trägt der das Muster nicht, blieb die Ersatzdatei ohne Titel-ID. Jetzt wird zuerst `sce_sys/nptitle.dat` gelesen, eine kleine Metadatendatei direkt neben der `param.json`. In allen 32 geprüften Backups war sie vorhanden und stimmte mit der `param.json` überein. Der Ordnername bleibt der Notnagel, falls die Datei fehlt.

### Drei zusätzliche Werkzeuge

Im Menü **WEITERE TOOLS** liegen jetzt auch **PKG-MERGER** und **PARAM/MANIFEST** (bisher eigene Schaltflächen in der Titelleiste) sowie drei neue Einträge:

- **SELF-Inspektor** – zeigt den Aufbau einer `eboot.bin`, `.self`, `.sprx` oder `.prx`: Container-Art, eingebettetes ELF, Signaturkategorie und die Segmenttabelle. Es wird nur gelesen, nichts entschlüsselt.
- **Dump umbenennen** – schlägt aus Title-ID, Titel und Version einen sprechenden Ordnernamen vor und benennt auf Wunsch um.
- **Debug-PKG bauen** – erzeugt aus einem Dump-Ordner einen strukturell gültigen, **unsignierten** `.pkg`-Container für Struktur- und Werkzeugtests.

### Kleinere Verbesserungen

- Die Cover-Vorschau in der Sidebar sitzt jetzt mittig in ihrer Fläche – vorher klebte sie oben und war seitlich um ein Pixel versetzt.
- Beim Sprachwechsel werden auch die Einträge im Menü **WEITERE TOOLS** übersetzt; sie blieben bisher in der Sprache des Programmstarts stehen.
- Beim Programmstart erscheint keine Warnung der Bildbibliothek mehr.

---

## v1.8.32 – 15.08.2026

Alle acht Aufgaben wurden mit echten Backups in allen Formaten durchgetestet (19 Konvertierungen, rund 10 GB Ergebnisse, dazu Uploads auf die Konsole). Was dabei auffiel, ist hier behoben.

### Behobene Fehler

- **Kommandozeilenmodus brach an einem Pfeilzeichen ab.** Leitete man die Ausgabe in eine Datei um, beendete ein „→" in einer Protokollzeile die ganze Aufgabe mit „Unerwarteter Fehler" – obwohl die Arbeit bereits fertig war. Betraf vier von neunzehn Testläufen.
- **Aufgabe 4 konnte eine `.ffpkg` nicht neu aufbauen.** Die Auswahlliste bot „.ffpkg (Neuvalidierung)" an, der Start brach aber mit „Quelle und Zielformat sind identisch" ab.
- **Validator meldete einwandfreie Backups als beschädigt.** `sce_sys/pfs-version.dat` galt als Pflichtdatei; von 32 geprüften Backups fehlt sie bei zweien. Sie ist jetzt eine Empfehlung – fehlt sie, gibt es eine Warnung statt eines Fehlschlags. `eboot.bin` und `param.json` bleiben Pflicht.
- **Validator hielt zwei reguläre Containerformen für kaputt.** Ein aus `.exfat` oder `.ffpkg` gebauter Container enthält absichtlich das jeweilige Abbild; das wurde als „falsch verschachtelt" gemeldet. Alle drei Bauformen werden jetzt erkannt, die tatsächlich fehlerhafte weiterhin gemeldet.
- **Eingebettete Abbilder bekamen verstümmelte Namen.** Aus `Spiel (01.003.000).exfat` wurde im Container `PPSA19015.003.000).exfat`. Der Originalname bleibt jetzt erhalten.
- **Wiederherstellen meldete einen Fehler, wenn es nichts zu tun gab.** Hat das Spiel die Bibliothek nie selbst mitgebracht, gibt es keine Sicherung – das ist der erwartete Zustand und kein Fehlschlag mehr.

### Bibliothek zeigt Container-Titel

- In einer Sammlung aus reinen Containerdateien blieb bei jedem Eintrag „–" stehen. Titel, Title-ID und Version werden jetzt aus dem Dateinamen gelesen; liegt der zugehörige Dump-Ordner daneben, gelten weiterhin dessen echte Werte.

### Konfigurationseditor erhält die Datei

- Beim Zurückschreiben von `config.ini` auf die PS5 wurde die Datei aus den Einträgen neu aufgebaut – Kommentare und die auskommentierte Vorlage gingen dabei verloren. Jetzt wird die vorhandene Datei bearbeitet: Kommentare bleiben, geänderte Werte werden ersetzt, entfernte Einträge auskommentiert statt gelöscht.

### Schnellere Übertragung zur PS5

- Der übliche FTP-Payload schaffte im Test 1,5 MB/s; 249 MB brauchten damit fast drei Minuten. Läuft der mitgelieferte **zftpd** auf der Konsole, wird er jetzt bevorzugt. Läuft er nicht, fragt das Programm einmal nach, ob es ihn an die Konsole schicken soll – bei „Nein" bleibt alles beim Alten.

---

## v1.8.31 – 15.08.2026

### Unvollständige Dumps fallen auf

- Fehlen im Quellordner Pflichtdateien wie `eboot.bin` oder `sce_sys/param.json`, erscheint **vor dem Start** ein Hinweis mit den fehlenden Namen. Die Aufgabe lässt sich trotzdem starten – gedacht ist der Hinweis für den Fall, dass ein Backup unbemerkt unvollständig kopiert wurde.
- Aufgabe 8 hat fehlende Pflichtdateien bisher nur beim Prüfen eines **Ordners** gemeldet. Jetzt meldet sie dieselben Dateien auch beim Prüfen einer fertigen `.ffpfsc`/`.ffpfs`-Datei. Ein aus einem unvollständigen Backup gebauter Container fällt damit auch nachträglich auf.
- Beide Stellen verwenden dieselbe Liste, damit Ordner und Container nicht zu unterschiedlichen Urteilen kommen.

### Falsch verschachtelte Container werden erkannt

- Ein `.ffpfsc` besteht aus zwei Ebenen: außen der Container, innen die Spieldateien. Ging beim Erzeugen etwas schief, konnte dazwischen eine weitere Ebene liegen – von außen sah die Datei normal aus, auf der Konsole war sie unbrauchbar.
- Aufgabe 8 schaut jetzt eine Ebene tiefer und meldet solche Dateien als fehlgeschlagen, mit Angabe dessen, was dort statt der Spieldateien liegt.
- Die Datei wird dafür **nicht** entpackt: Gelesen wird nur das Inhaltsverzeichnis der inneren Ebene – bei einer 392-MB-Datei rund 750 Kilobyte in unter einer Zehntelsekunde.
- Neu im Protokoll: `nesting`, `inner_files`, `inner_dirs` und `critical_files`.

---

## v1.8.30 – 15.08.2026

### Rechner nach getaner Arbeit herunterfahren

- Neues Ankreuzfeld unter TEMP-ORDNER: **Rechner nach erfolgreichem Abschluss herunterfahren**. Damit lassen sich lange Konvertierungen unbeaufsichtigt laufen lassen.
- Ist eine Aufgabe **fehlgeschlagen oder abgebrochen**, bleibt der Rechner an – die Fehlermeldung bleibt lesbar. Maßgeblich ist dabei das Ergebnis der Aufgabe selbst, nicht der angezeigte Text.
- Vor dem Herunterfahren erscheint ein Fenster mit 60-Sekunden-Countdown. Ein Klick auf „Abbrechen – Rechner anlassen" oder die ESC-Taste hält den Rechner an.
- Danach löst das Programm erst alle gemounteten Abbilder, entfernt die temporären Arbeitsdateien und schreibt das Protokoll auf die Festplatte. Erst dann fährt Windows herunter – ohne Rückfragen und ohne dass hängengebliebene Laufwerke oder Temp-Reste zurückbleiben.
- Bei aktivem Ankreuzfeld entfällt die Erfolgsmeldung zum Wegklicken; sie würde auf eine Bestätigung warten, die niemand gibt. Der Erfolg steht in Statuszeile und Protokoll.
- Die Einstellung wird gespeichert. Im Kommandozeilenmodus gibt es dafür den Schalter `--shutdown-on-success`.
- Hinweis: Das Herunterfahren erfolgt ohne Rückfragen und beendet auch andere Programme; ungespeicherte Arbeit dort geht verloren. Im Countdown-Fenster steht das noch einmal.

---

## v1.8.29 – 15.08.2026

### Keine Restflächen mehr auf dem Hintergrundbild

- Unten rechts stand dauerhaft ein kleines helles Rechteck. Dort sitzt die Anzeige für CPU-, RAM- und Temp-Auslastung, die außerhalb einer laufenden Aufgabe nur ihren Text verlor, aber sichtbar blieb. Jetzt verschwindet sie ganz und taucht erst wieder auf, wenn eine Aufgabe läuft.
- Die Größenangabe neben der Fortschrittsleiste hinterlegte ihren Text über die volle Spaltenbreite – das sah aus wie eine zweite, leere Fortschrittsleiste. Die Fläche ist jetzt so breit wie die Angabe selbst. Der reservierte Platz bleibt unverändert, längere Angaben haben sogar etwas mehr Raum als vorher.
- Direkt nach dem Programmstart und nach jeder Änderung der Fenstergröße zeigten Überschrift, Statuszeile und der Spielname in der Sidebar für einen Moment wieder einen Kasten. Beide Fälle werden jetzt automatisch nachgezeichnet.
- Ein Design-Wechsel im laufenden Betrieb ließ einzelne Beschriftungen in der Farbe des alten Designs zurück. Alle Beschriftungen wechseln jetzt gemeinsam.

### Schneller FTP-Payload wird gefunden

- Das mitgelieferte **zftpd** lauscht auf der Konsole auf Port 2120. Die automatische Suche kannte nur 2121, 1337 und 21 – wer zftpd über den JS Loader startete, wurde nicht gefunden. Port 2120 wird jetzt mitgeprüft.
- Scheitert die Verbindung im AMPR Picker, nennt die Meldung jetzt die geprüften Ports und weist auf die mitgelieferten Payloads hin: zftpd (Port 2120, schnellste Übertragung) und ftpsrv-ps5 (Port 2121).

### Lizenzen der mitgelieferten Payloads

- Neue Datei `THIRD_PARTY_LICENSES.md` mit den Lizenzbedingungen der mitgelieferten Fremdkomponenten. Sie liegt der Windows-EXE bei und lässt sich im Fenster CREDITS direkt öffnen.

---

## v1.8.28 – 15.08.2026

### Beschriftungen ohne Kasten

- Bei eingestelltem Hintergrundbild lag hinter QUELLE, ZIELFORMAT, KOMPRESSION, ZIELORDNER und TEMP-ORDNER ein heller Kasten. Jetzt ist nur noch die Schrift zu sehen, das Bild läuft ungestört durch.
- Der Hinweis unter dem Zielformat („Quelle: Dump-Ordner") hatte bisher sogar eine vollflächige Fläche – auch er steht jetzt frei auf dem Bild und passt sich beim Wechsel der Aufgabe oder der Sprache an.
- Ebenso randlos sind Überschrift, Zeile darunter, Statuszeile unten und die Beschriftungen in der Sidebar einschließlich des Spielnamens unter dem Cover.
- Nur die Größenangabe neben der Fortschrittsanzeige behält bewusst eine leicht abgedunkelte Fläche, damit sie über unruhigen Bildstellen lesbar bleibt.

---

## v1.8.27 – 15.08.2026

### AMPR-Versionen sind mitgeliefert

- Die AMPR-EMU- und PlayGo-Dateien gehören jetzt zum Programm. Aufgabe 7 findet sie von allein; der Versionsordner muss nicht mehr ausgewählt werden.
- Ein selbst gewählter Ordner hat weiterhin Vorrang, falls du eigene Versionen verwenden möchtest.
- In der Windows-EXE sind die Dateien eingebettet – auch dort ist keine Auswahl nötig.

### Hintergrundbilder zur Auswahl

- Im Design-Fenster lassen sich mitgelieferte Hintergrundbilder direkt aus einer Liste übernehmen.
- Ein eigenes Bild kann weiterhin über die Dateiauswahl gesetzt werden; diese startet jetzt im mitgelieferten Ordner.

### Zwei Werkzeuge entfernt

- **Y2JB** und **Dump umbenennen** sind aus dem Menü "Weitere Tools" entfernt. Dort verbleiben MicroMount und der AMPR-Index-Builder.
- Der JS Loader ist davon nicht betroffen und bleibt unverändert erhalten.

### AMPR und PlayGo getrennt wählbar

- Für `libSceAmpr.sprx` und `libScePlayGo.sprx` gibt es jetzt je ein eigenes Auswahlfeld. Vorher ließ sich nur eine der beiden Dateien setzen, obwohl sie unterschiedliche Versionsstände haben.
- Vorausgewählt ist nur `libSceAmpr.sprx` – das eigentliche APR-EMU-Modul. `libScePlayGo.sprx` stammt aus einem separaten Projekt und meldet dem Spiel, dass alle PlayGo-Inhalte bereits installiert sind; er wird nur bei Titeln gebraucht, die Inhalte als fehlend behandeln, und muss deshalb bewusst dazugewählt werden.
- Einzelne Felder lassen sich auf „nicht ändern" stellen, um nur eine der beiden Dateien zu tauschen.
- Wiederherstellen und Entfernen erfassen weiterhin beide Dateien.

### JS Loader findet eigene Payloads

- Die Schnellauswahl im JS Loader suchte in der Windows-EXE nur im eingebetteten Bereich. Eigene `.elf`-Dateien, die neben das Programm gelegt wurden, blieben dadurch unsichtbar. Jetzt wird beides berücksichtigt.

### Einstellungen gehen nicht mehr verloren

- Beim Speichern wurde die Einstellungsdatei zuerst geleert und dann neu geschrieben. Wurde in diesem Moment gelesen – oder brach das Programm dazwischen ab –, waren Temp-Ordner, PS5-Adresse, Hintergrundbild und die übrigen Werte verloren.
- Die Datei wird jetzt vollständig neben der alten aufgebaut und erst danach in einem Schritt ersetzt. Ist sie kurzzeitig belegt, wird der Vorgang wiederholt statt aufzugeben.

### Groessenhinweis fuer das Hintergrundbild

- Bei den Einstellungen steht jetzt auch fuer das Haupt-Hintergrundbild eine Groessenempfehlung (1920 x 1020 Pixel) – bisher gab es die nur beim Sidebar-Bild.
- Der Hinweis erklaert ausserdem, dass das Bild auf die Fenstergroesse gestreckt wird und ein abweichendes Seitenverhältnis daher verzerrt.

### Beschriftung von Aufgabe 7

- Der Aufgabenknopf zeigte einen internen Schlüsselnamen statt "7. AMPR EMU Manager".

---

## v1.8.26 – 15.08.2026

### Aufgabe 7 ist jetzt der AMPR EMU Manager

- Aus dem bisherigen fakelib Manager wurde ein Werkzeug rund um den AMPR-Emulator. Die früheren Datei-Aktionen (fakelib hinzufügen/entfernen, einzelne Dateien ins Stammverzeichnis kopieren) sind entfallen.
- Die Aufgabe arbeitet weiterhin mit Dump-Ordnern sowie `.ffpfsc`-, `.ffpfs`-, `.exFAT`- und `.ffpkg`-Quellen.

### AMPR-Versionen verwalten

- Aus einem frei wählbaren Ordner werden alle vorhandenen AMPR-EMU- und PlayGo-Ausgaben eingelesen, nach Version sortiert und mit Variante (`debug` / `no debug`) angezeigt.
- Die im Spiel installierte Version wird über ihre Prüfsumme erkannt und benannt – auch dann, wenn sie nicht selbst eingespielt wurde.
- Vor dem ersten Austausch wird die vom Spiel mitgelieferte Datei als `.orig` gesichert und lässt sich jederzeit zurückholen. Eine vorhandene Sicherung wird bei weiteren Wechseln nicht überschrieben.
- Eigene `.sprx`/`.prx`-Dateien können statt einer Version aus dem Ordner übernommen werden.

### ampr_emu.index automatisch

- Nach jedem Eingriff wird die Indexdatei neu aufgebaut, damit sie zum tatsächlichen Dateibestand passt.
- Der Index lässt sich zusätzlich direkt aus dem Spielverzeichnis einer angeschlossenen PS5 erzeugen und dorthin zurückschreiben.

### AMPR Picker: direkt auf der Konsole arbeiten

- Ein FTP-Browser zeigt die Spielordner der PS5, mit Schnellzugriffen auf `/data/etaHEN/games`, `/data/homebrew`, `/mnt/data`, `/user/app` und `/mnt/usb0`.
- Vor dem Indexieren wird geprüft, ob der gewählte Ordner wirklich ein Spielverzeichnis ist.
- AMPR- und PlayGo-Bibliothek lassen sich als Paar auf die Konsole übertragen und der Index anschließend neu bauen – ohne das Spiel-Image neu zu erstellen. Ein fehlender `fakelib`-Ordner wird dabei angelegt.
- Der FTP-Port wird selbst ermittelt (2121, 1337, 21), er muss nicht bekannt sein.

### FileZilla wird zuverlässiger gefunden

- Zusätzlich zu den Standardpfaden werden jetzt die Windows-Deinstallationseinträge ausgewertet und, falls nötig, die Laufwerke durchsucht. Damit wird FileZilla auch an ungewöhnlichen Installationsorten gefunden.
- Ein leerer Registry-Eintrag aus einer früheren Deinstallation führte dazu, dass im Arbeitsverzeichnis nach `filezilla.exe` gesucht wurde.

---

## v1.8.25 – 14.08.2026

### Aufgabe 7 schreibt .ffpfsc und .ffpfs wieder korrekt zurück

- Nach einer `fakelib`-Änderung an einer `.ffpfsc`- oder `.ffpfs`-Datei wurde eine Ebene zu viel eingepackt. Die Datei ließ sich zwar öffnen und wurde als gültig gemeldet, enthielt beim Entpacken aber nur einen einzelnen Container statt der Spieldateien – auf der Konsole unbrauchbar. Betroffen waren ausschließlich `.ffpfsc`/`.ffpfs` als Quelle; Dump-Ordner, `.exFAT` und `.ffpkg` waren nicht betroffen.
- Eine `.ffpfs`-Datei bleibt jetzt auch bei Aufgabe 7 unkomprimiert, statt trotz Endung komprimiert geschrieben zu werden.

### Fehlerhafte Ergebnisse werden nicht mehr als Erfolg gemeldet

- Beim Zielformat "Dump-Ordner" prüft die Abschlusskontrolle jetzt, ob wirklich ein Spiel-Dump entstanden ist. Vorher genügte irgendeine Datei im Zielordner, sodass ein unbrauchbares Ergebnis als "erfolgreich abgeschlossen" durchging.
- Schlägt die Abschlussprüfung fehl, zeigt das Statusfeld das auch an, statt weiter "erfolgreich" zu melden.

### Aufgabe 7 über die Kommandozeile

- Der `--cli`-Modus deckt jetzt wirklich alle acht Aufgaben ab. Aufgabe 7 wartete bisher ohne sichtbares Fenster endlos auf eine Eingabe im Auswahldialog.
- Die Aktion wird über `--fakelib-action` gewählt, ergänzt um `--fakelib-src`, `--fakelib-files`, `--fakelib-dirs`, `--fakelib-items` und die APR-Optionen. Fehlt die Angabe, bricht der Aufruf sofort mit einem Hinweis ab.

### Klare Meldung bei fehlenden Administratorrechten

- Beim Erzeugen einer `.ffpkg` ohne erhöhte Rechte erscheint sofort ein verständlicher Hinweis. Vorher wurden erst drei UFS2-Profile nacheinander durchprobiert, die alle mit einer technischen Windows-Fehlernummer abbrachen.

### Temporäre Dateien werden restlos entfernt

- Ordner mit schreibgeschützten Dateien – wie sie beim Entpacken einer `.ffpkg` entstehen – blieben bisher im Temp-Verzeichnis liegen und belegten pro Durchlauf mehrere hundert Megabyte.

### Englische Oberfläche

- Die Zielformate "Dump-Ordner" und ".ffpfs" ließen sich bei englischer Spracheinstellung über die Kommandozeile nicht auswählen.
- Die Abschlussmeldungen erscheinen jetzt ebenfalls auf Englisch, und der Rückgabewert der Kommandozeile meldet einen fehlgeschlagenen Lauf auch bei englischer Einstellung korrekt als Fehler.

### Protokollmeldungen

- Zwischenschritte tragen keine feste Aufgabennummer mehr. Da dieselben Schritte aus mehreren Aufgaben heraus laufen, stand dort teilweise eine andere Nummer als die tatsächlich gewählte Aufgabe.

---

## v1.8.24 – 14.08.2026

### Neue Werkzeuge in "Weitere Tools"

- **MicroMount**: Konfigurationseditor für das gleichnamige Drittanbieter-Mount-Tool (`/data/micromount/config.ini`), analog zu SHADOWMOUNT+, zusätzlich mit Payload-Versand per TCP an die PS5.
- **AMPR-Index-Builder**: Baut aus einem lokalen Ordner die Indexdatei `ampr_emu.index` für den AMPR-Dateiresolver.

Diese Werkzeuge sind über einen neuen Knopf "Weitere Tools" in der Titelleiste erreichbar, um die Knopfreihe nicht zu überladen.

### Titelleiste aufgeräumt

- Der Programmname/Version-Text links in der Titelleiste wurde entfernt, damit mehr Platz für die Werkzeug-Knöpfe bleibt.

### Realistischere Speicherplatz-Warnung

- Vor Aufgabe 2/4 wird jetzt die tatsächlich benötigte Zielgröße geschätzt (direkt aus dem Container gelesen, ohne ihn zu entpacken), statt einer festen 6-GB-Schwelle. Das warnt zuverlässig, bevor bei sehr großen Spielen mitten in der Verarbeitung der Speicherplatz ausgeht.

---

## v1.8.23 – 13.08.2026

### Automatische Bereinigung alter Temp-Dateien

- Die Rückfrage beim Start ("Alte Temp-Dateien gefunden") wird nicht mehr angezeigt.
- Gefundene alte temporäre PS5Conv-Dateien und -Ordner werden stattdessen automatisch im Hintergrund gelöscht.

### Sidebar-Logo-Bereich repariert

- Hinter "PS5 DUMP & IMAGE CONVERTER" sowie den Symbolen darüber in der Sidebar war bei aktivem Sidebar-Hintergrundbild noch ein grauer Kasten samt dünnem Rahmen sichtbar, unabhängig vom gewählten Design.
- Dieser Bereich zeigt das Hintergrundbild jetzt lückenlos, genau wie die übrigen Beschriftungen im Hauptfenster.

---

## v1.8.22 – 13.08.2026

### Zusatzfenster modernisiert

- Diagnose, KLog, Bibliothek, ShadowMount+, Param/Manifest-Editor, PKG-Merger, Design und Einstellungen wurden optisch überarbeitet und wirken nun deutlich weniger rustikal.
- Design- und Einstellungen-Fenster lassen sich jetzt in der Größe anpassen und besitzen bei Bedarf einen Scrollbereich – dadurch bleiben alle Knöpfe (z. B. ganz unten im Einstellungen-Fenster) auch bei höherer Windows-Bildschirmskalierung erreichbar.

### Hauptfenster überarbeitet

- Start- und Abbrechen-Knopf sowie die Ordner-Auswahl-Knöpfe (Quelle, Ziel, Temp) sind jetzt größer, abgerundet und deutlich besser lesbar.
- Mehr Abstand und größere Schrift in der Quelle-Karte und den Eingabefeldern.

### Hintergrundbild verfeinert

- Letzte schmale Ränder ohne Hintergrundbild in der Sidebar, im Content-Bereich und in der Quelle-Karte entfernt – das Bild reicht jetzt lückenlos bis an den Rand.
- Die Werkzeugleiste mit den Knöpfen Diagnose, KLog, Bibliothek, ShadowMount+, Param/Manifest und PKG-Merger zeigt bewusst kein Hintergrundbild mehr, damit die Knöpfe dort klar hervortreten.
- Neu in den Einstellungen: ein eigenes Hintergrundbild nur für die Sidebar (Aufgaben-Knöpfe links, Spielvorschau), unabhängig vom Hintergrundbild im Hauptbereich wählbar und ebenso jederzeit zurücksetzbar.
- Ein Wechsel des Designs (Dunkel/Mittel/Hell) ohne Neustart aktualisiert jetzt auch das Hintergrundbild und die Kartenbeschriftungen korrekt mit.

### Schärfere Darstellung bei Windows-Skalierung

- Die App ist jetzt DPI-bewusst und wird bei Windows-Bildschirmskalierung über 100 % scharf statt unscharf/vergrößert dargestellt.

---

## v1.8.21 – 13.08.2026

### Letzte bildlose Kästen im Hauptfenster entfernt

- Überschrift samt Untertitel, die Statuszeile unten rechts und die Start/Abbrechen-Leiste (inkl. Fortschritts- und Größenanzeige) zeigten noch einen dunklen Kasten statt des Hintergrundbilds, obwohl Titelleiste, Sidebar und Content-Bereich es bereits zeigten.
- Alle vier Bereiche zeigen das Hintergrundbild jetzt ebenfalls, Text bleibt weiterhin gut lesbar.

---

## v1.8.20 – 13.08.2026

### Hintergrundbild jetzt überall im Fenster sichtbar

- Titelleiste (oben) und Sidebar (links) waren bisher durchgehend deckende Flächen ohne jede Spur des Hintergrundbilds, obwohl der Content-Bereich rechts es schon zeigte.
- Beide zeigen das Hintergrundbild jetzt ebenfalls, während Buttons und Text weiterhin gut lesbar auf ihrer eigenen Hintergrundfarbe stehen.

---

## v1.8.19 – 12.08.2026

### Quelle-Karte im hellen Design korrigiert

- Im hellen Design wurde das Hintergrundbild bisher genauso stark in die Quelle-Karte eingemischt wie im dunklen und mittleren Design. Da das Hintergrundbild meist dunkel ist, wirkte die eigentlich weiße Karte dadurch unnötig dunkel-gräulich.
- Die Karte zeigt jetzt im hellen Design nur noch einen dezenten Hauch des Bildes und bleibt überwiegend hell. Dunkles und mittleres Design sind unverändert.

---

## v1.8.18 – 12.08.2026

### Beschriftungen ohne störenden Kasten

- QUELLE, ZIELFORMAT, KOMPRESSION/WORKER, ZIELORDNER und TEMP-ORDNER zeigen jetzt keinen sichtbaren, farblich unpassenden Kasten mehr, sondern den passenden Ausschnitt des Hintergrundbilds direkt hinter dem Text – gut lesbar und ohne Umrandung.
- Das Hintergrundbild in der Quelle-Karte läuft jetzt an jeder Stelle nahtlos in einem Stück durch, ohne sichtbaren Übergang zwischen Karte und restlichem Fenster.

### Wackeln beim Start behoben

- **Behoben:** Die Karte im Hauptbereich konnte beim Programmstart kurz sichtbar wackeln bzw. die Größe ändern. Das ist jetzt behoben.

### Kleinere Korrektur am Param-/Manifest-Editor

- Das Fenster zum Bearbeiten von `param.json`/`manifest.json` ist jetzt von Anfang an groß genug, sodass alle Knöpfe am unteren Rand sofort sichtbar sind, ohne das Fenster erst manuell zu vergrößern.

---

## v1.8.17 – 12.08.2026

### Hintergrundbild jetzt tatsächlich sichtbar

- Das in v1.8.16 eingeführte Hintergrundbild (Standard oder selbst gewählt) war bisher komplett unsichtbar, weil die Oberfläche es vollständig überdeckte.
- Jetzt ist es im Hauptbereich (rund um Quelle, Zielformat, Zielordner, Temp-Ordner) sichtbar, mit der gewohnten Deckkraft.

---

## v1.8.16 – 12.08.2026

### Eigenes Hintergrundbild wählbar

- Neuer Knopf **EINSTELLUNGEN** in der Titelleiste (neben DESIGN).
- Dort lässt sich ein beliebiges Bild als Hintergrund fürs Hauptfenster wählen (JPG, PNG, BMP, GIF, WEBP, TIFF usw.) – es wird automatisch in das passende Format umgewandelt, egal wie es ursprünglich vorliegt.
- Das Bild wird mit 30 % Deckkraft angezeigt, sofort und ohne Neustart, und bleibt auch nach einem Neustart des Programms erhalten.
- Über **Zurücksetzen** lässt sich jederzeit wieder der Standard-Hintergrund herstellen.

---

## v1.8.15 – 12.08.2026

### Fehlende param.json automatisch erstellen lassen

- Fehlt beim Erstellen von `.exfat`, `.ffpkg`, `.ffpfsc` oder `.ffpfs` die Datei `sce_sys/param.json` oder ist sie beschädigt, fragt das Programm jetzt: „Soll automatisch eine param.json dafür erstellt werden?“ – mit Ja/Nein.
- Bei **Ja** wird eine gültige param.json angelegt (die Titel-ID wird nach Möglichkeit aus dem Datei-/Ordnernamen erkannt, z. B. `PPSA04263`) und der Bau läuft normal weiter.
- Bei **Nein** bricht der Bau wie bisher mit einer klaren Meldung ab.

---

## v1.8.14 – 12.08.2026

### Nochmal schnellere Titel-Infos bei großen Spielen

- Bei sehr großen `.ffpfsc`-Dateien (viele tausend Dateien) erschienen die Titel-Infos bisher langsamer als bei kleineren Spielen. Das ist jetzt behoben – die Anzeige ist durchgängig schnell, egal wie viele Dateien das Spiel enthält.

### Schutz vor unvollständigen `.exfat`/`.ffpkg`-Dateien

- Fehlt in der Quelle die Datei `sce_sys/param.json` oder ist sie beschädigt, bricht die Erstellung von `.exfat`- und `.ffpkg`-Dateien jetzt sofort mit einer klaren Meldung ab, statt eine Datei zu erzeugen, die die PS5 anschließend nicht als gültigen Titel erkennt.

---

## v1.8.13 – 12.08.2026

### Schnellere Anzeige der Titel-Infos

- Wenn du dir die Infos zu einer `.ffpfsc`-Datei anzeigen lässt (Titel, Titel-ID, Version, Region), erscheinen diese jetzt spürbar schneller.
- Am angezeigten Inhalt ändert sich nichts – nur das Tempo.

---

## v1.8.12 – 11.08.2026

### Komplette englische Übersetzung

- Die Oberfläche ist jetzt durchgängig zweisprachig. Wenn du auf Englisch umschaltest, ist wirklich *alles* auf Englisch – auch alle Dialoge, Zusatzfenster und Meldungen. Vorher war nur ein Teil übersetzt.
- Sieben alte Werkzeuge, die über keinen Knopf mehr erreichbar waren, wurden entfernt. Am Funktionsumfang der acht Hauptaufgaben und der übrigen Werkzeuge ändert sich dadurch nichts.

---

## v1.8.11 – 10.08.2026

### Keine automatische Berichtsdatei mehr

- Nach einer Konvertierung wird keine zusätzliche `.json`-Berichtsdatei mehr im Zielordner abgelegt.
- Es erscheint nur noch die Meldung „Vorgang erfolgreich abgeschlossen!“.

---

## v1.8.10 – 10.08.2026

### Wichtiger Fehler bei der Grundkonvertierung behoben

- **Behoben:** Bei Aufgabe 1 (Dump-Ordner → `.ffpfsc`/`.ffpfs`) hatte die erzeugte Datei eine zusätzliche, ungewollte innere Verpackungsebene. Die Dateien haben jetzt denselben Aufbau wie bekannt funktionierende Referenzdateien. *(Eine endgültige Bestätigung auf echter Hardware steht noch aus.)*
- **Neu:** `.exfat`-Dateien werden nach dem Erstellen zusätzlich auf Vollständigkeit geprüft – unvollständige Dateien werden nicht mehr übernommen.
- **Verbessert:** `.ffpfs`-Dateien lassen sich jetzt in allen Aufgaben als Quelle verwenden, nicht mehr nur zum Prüfen.

---

## v1.8.9 – 10.08.2026

### Vollständigkeitsprüfung für `.ffpkg`-Dateien

- Nach dem Erstellen einer `.ffpkg`-Datei wird jetzt geprüft, ob wirklich alle Dateien aus dem Quellordner enthalten sind.
- Das hilft besonders bei Ordnern mit sehr vielen kleinen Dateien: Eine unvollständige Datei wird automatisch verworfen statt fälschlich als fertig übernommen.

---

## v1.8.8 – 10.08.2026

### Design-Wechsel mehrfach hintereinander möglich

- Du kannst das Design jetzt auch mehrmals nacheinander wechseln und anwenden, ohne dass der automatische Neustart beim zweiten Mal fehlschlägt.

---

## v1.8.7 – 10.08.2026

### Störende Meldung beim Neustart reduziert

- Die harmlose Meldung „Failed to remove temporary directory“ nach einem Design-Wechsel tritt jetzt seltener auf.
- Falls sie doch erscheint, kannst du sie gefahrlos mit OK bestätigen – das Programm funktioniert normal weiter.

---

## v1.8.6 – 09.08.2026

### Automatischer Neustart robuster gemacht

- Der Neustart nach einem Design-Wechsel ist jetzt zuverlässiger und stürzt nicht mehr durch zeitliche Überschneidungen ab.

---

## v1.8.5 – 09.08.2026

### Absturz beim Programmstart behoben

- **Behoben:** Die Windows-Version (`.exe`) stürzte direkt beim Start ab, sobald „Ziehen & Ablegen“ (Drag & Drop) aktiv wurde.
- Das Ziehen von Ordnern in die Felder für Quelle/Ziel/Temp funktioniert jetzt auch in der `.exe`.

---

## v1.8.4 – 09.08.2026

### Absturz nach Design-Wechsel vollständig behoben

- Der automatische Neustart nach einem Design-Wechsel funktioniert jetzt auch in der Windows-`.exe` zuverlässig und ohne Fehlermeldungen. *(Korrigiert einen unvollständigen ersten Behebungsversuch aus v1.8.2/v1.8.3.)*

---

## v1.8.2 – 09.08.2026

### Design wird jetzt überall korrekt angezeigt

- Nach dem Anwenden eines neuen Designs startet das Programm automatisch neu, damit das gewählte Farbschema wirklich in allen Fenstern korrekt erscheint.
- Läuft gerade eine Aufgabe, wird der Neustart bis nach deren Abschluss zurückgestellt – eine laufende Konvertierung wird nie unterbrochen.

---

## v1.8.1 – 09.08.2026

### Überarbeitete Farbdesigns und aufgeräumte Titelleiste

- Alle drei Farbdesigns (Hell, Mittel, Dunkel) haben jetzt sichtbare Kontraste – Karten, Buttons und Listen sind in jeder Variante gut lesbar.
- **Behoben:** Beim Überfahren mancher Buttons mit der Maus war der Text vorher unsichtbar (weiß auf hell).
- Dropdown-Listen und Tabellen passen sich jetzt ebenfalls dem gewählten Design an.
- Die Titelleiste zeigt nur noch aktiv genutzte Werkzeuge.

---

## v1.8.0 – 09.08.2026

### Großes Funktions-Update: Aus dem Konverter wird eine Werkzeug-Suite

Diese Version ergänzt viele neue Werkzeuge rund um die acht Hauptaufgaben, ohne die bewährte Konvertierung zu verändern. Neu unter anderem:

- **PKG-Merger** – geteilte Pakete wieder zusammenfügen
- **Param-/Manifest-Editor** – Metadaten bearbeiten (`param.json`/`manifest.json`)
- **Bibliothek** – mehrere Ordner durchsuchen, mit Cover-Anzeige
- **Diagnosebericht** – erzeugt einen Bericht zu Version/System/Log (Zugangsdaten werden geschwärzt)
- **Klog & ShadowMount+** – Werkzeuge für die PS5-Kommunikation
- **Deutsch/Englisch-Umschaltung** (Grundgerüst)
- **Neues Format `.ffpfs`** (unkomprimierte Variante)
- **Ziehen & Ablegen** (Drag & Drop), CLI-Modus, wählbare Kompressionsstufe, einstellbare Worker-Anzahl, Tastenkürzel

Außerdem behoben: mehrere Programmabstürze in Bibliothek, Diagnosebericht und PKG-Merger sowie eine Fortschrittsanzeige, die bei Aufgabe 1 nahe 95 % einzufrieren schien.

---

## v1.7.76 bis v1.7.90 – Zuverlässige `.ffpkg`-Erstellung

Diese Versionsreihe drehte sich vor allem darum, das Erstellen von `.ffpkg`-Dateien schrittweise **fehlerfrei und zuverlässig** zu machen. Für dich als Nutzer zählt vor allem das Ergebnis:

- Eine `.ffpkg`-Datei wird erst dann als fertig übernommen, wenn sie eine vollständige Prüfung bestanden hat. Fehlerhafte oder unvollständige Dateien werden automatisch verworfen statt ausgegeben.
- Frühere Abbrüche mit Meldungen wie „BAD MAGIC NUMBER“ oder beschädigte Dateien auf dem Ziellaufwerk gehören damit der Vergangenheit an.
- Die Fortschrittsanzeige während der `.ffpkg`-Erstellung zeigt jetzt den echten Fortschritt.
- Auch Ordner mit sehr vielen kleinen Dateien werden korrekt und vollständig verarbeitet.
- `.ffpkg` kann seit v1.7.84 nicht nur gelesen, sondern auch neu erzeugt werden.

*Die vielen Zwischenversionen (v1.7.76–v1.7.90) waren nötig, weil jeder Schritt an echten Beispieldateien getestet und der nächste Fehler gezielt behoben wurde.*

---

## v1.0.1 bis v1.7.75 – Grundlagen

In dieser frühen Phase entstand das eigentliche Programm: die erste Programmstruktur, die Windows-Oberfläche und die Grundfunktionen zum Packen, Entpacken und Konvertieren von PS5-Dumps. Zu diesen frühen Ständen liegen keine lückenlosen Einzelnotizen mehr vor, deshalb sind sie hier nur zusammengefasst.

---

*Hinweis: Sehr technische Details (Bauprozess, interne Tests, Runtime-Versionen usw.) sind in diesem Changelog absichtlich weggelassen. Sie finden sich bei Bedarf in den ausführlichen Release Notes.*
