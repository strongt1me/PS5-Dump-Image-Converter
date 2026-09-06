## Behoben: Nach dem Packen sah niemand hin

In der Voreinstellung lief nach dem Erstellen eines Abbilds **keine einzige
Kontrolle** — obwohl die Prüfstufe „Schnell“ genau das versprach und der
Hilfetext daneben es so beschrieb.

**Woran es lag.** Die voreingestellte Bauform ist exFAT, und dieser Zweig
fragte allein nach dem Schalter für die *vollständige* Prüfung. Der Schalter
für die schnelle Strukturprüfung steht standardmäßig an — ausgewertet wurde er
dort nie. Der andere Bauweg (PFS) hat ihn immer beachtet.

Jetzt prüft auch der exFAT-Weg. Gemessen kostet das 0,2 Sekunden auf 38 MB;
wer die Zeit sparen will, stellt die Prüfung auf „Aus“.

## Behoben: Drei Wege zu einem beschädigten Abbild, alle lautlos

Derselbe Bauweg nahm drei Quellen an, die der PFS-Weg von jeher ablehnt:

* **Eine Datei, die beim Lesen kürzer ist als angekündigt.** Der Rest wurde
  mit Nullen aufgefüllt, das Abbild behielt seine geplante Größe, und der
  Verzeichniseintrag nannte weiter die volle Länge. Nachgemessen: 200 000
  Nullen mitten in einer 300 000 Bytes großen `eboot.bin` — ohne ein Wort.
  Für den Lader der Konsole ist das ein Kopf, dessen Segmenttabelle in
  Nullen zeigt.
* **Namen mit Sonderzeichen.** Die Namensprüfsumme im Abbild rechnet nur mit
  ASCII; für alles andere weicht sie von der Tabelle ab, die die Konsole
  benutzt, und die Datei ist dort unauffindbar.
* **Verknüpfungen (Symlinks) im Dump-Ordner.** Sie fielen ersatzlos aus dem
  Abbild heraus. Ein Dump, der über `rsync`, ein Netzlaufwerk oder ein
  Festplattenabbild kam, kann welche tragen.

Alle drei brechen den Lauf jetzt mit einer benannten Meldung ab.

## Behoben: Auf dem Mac fror der Bildschirm beim allerersten Start ein

Startet man eine frisch geladene App aus dem Download-Ordner, führt macOS sie
schreibgeschützt aus einer Kopie aus. Das Programm weist darauf hin — und
dieser Hinweis erschien, während das Fenster noch unsichtbar war.

**Woran es lag.** Das Fenster ist beim Aufbau bewusst durchsichtig geschaltet,
damit es nicht halbfertig aufblitzt. Der Hinweis war für 1,2 Sekunden nach dem
Start eingeplant; dauerte der Aufbau länger, ging er in dieser Zeitspanne auf.
Ohne gemerkte Fenstergröße ist das Fenster dabei zugleich bildschirmfüllend
und hat den Fokus. Ein unsichtbares Fenster lag also über allem und wartete
auf einen Klick, den niemand sehen konnte — für den Anwender nicht von einem
eingefrorenen Bildschirm zu unterscheiden.

Der Hinweis wartet jetzt, bis das Fenster wirklich sichtbar ist, und gibt nach
zehn Sekunden auf. Er erscheint ohnehin nur in diesem einen Fall, also beim
ersten Start nach dem Laden.

## Behoben: „AMPR aktualisieren“ meldete immer „schon aktuell“

Der Knopf verglich die angebotenen Fassungen gegen den vorhandenen Bestand —
und in diesem Bestand zählte PlayGo mit. Dessen Nummer (0.5) liegt über jeder
AMPR-Fassung (zuletzt 0.3.6.6), also kam nie wieder etwas darüber. Nachgemessen
wurde ein Angebot 0.4.0 abgewiesen. Das traf jeden, ohne Zutun, von Anfang an.

Drei weitere Mängel am selben Weg:

* **Zwei getrennte Bestände im selben Programm.** Fassungen können an vier
  Orten liegen. Die Auswahl beim Erstellen las fest den mitgelieferten Ordner,
  der AMPR-Manager und der Automatiklauf nur den selbst gesetzten. Gemessen:
  13 Fassungen an der einen Stelle, 2 an der anderen — vorhanden waren 15.
  Jetzt sehen alle Stellen alle.
* **Die Variante zählte nicht mit.** Wer `0.3.6.6 no debug` hatte, bekam
  dieselbe Nummer als `debug` nie angeboten, obwohl das zwei verschiedene
  Dateien sind. Beide Reihen werden jetzt getrennt gezählt.
* **Eigene Ordnernamen wurden nicht verstanden.** Wer seine Ordner `nolog`
  und `log` nennt statt `no debug` und `debug`, galt als „unbekannte
  Variante“ — und die fehlenden Fassungen kamen nicht durch.

## Behoben: Der AMPR-Lauf räumte die config.ini der Konsole aus

Wer den Lauf die Einstellungen von ShadowMount+ korrigieren ließ, bekam eine
Datei zurück, in der **alle** bisherigen Einstellungen abgeschaltet waren —
Suchpfade, Port, Einhängepunkt. Nur die geänderten Zeilen überlebten.

Die Datei wurde dabei nicht kürzer, nur wirkungslos: Jede Zeile stand noch da,
mit einem Kommentarzeichen davor. Deshalb fiel es an der Konsole erst auf, wenn
nichts mehr gefunden wurde.

## Behoben: Dreizehn Fassungen lagen daneben, und der Lauf brach ab

Fehlten die AMPR-Bibliotheken im Dump, kannte das Programm dafür nur einen
gesondert eingestellten Ordner, in dem beide Dateien flach nebeneinander liegen
mussten. Genau diesen Aufbau hat der Versionsspeicher nicht. Im Automatikbetrieb
brach der Lauf deshalb ab, obwohl dreizehn Fassungen bereitlagen; in der
Oberfläche kam ein Ordner-Auswahldialog, direkt nachdem man eine Fassung
gewählt hatte.

Jetzt greift das Programm auf den Versionsspeicher zurück. Ein ausdrücklich
eingestellter Ordner behält seinen Vorrang.

## Behoben: Sechs Knöpfe konnten gar nicht scheitern

Handbuch öffnen, Lizenz öffnen, AMPR-Anleitung öffnen, Download-Ordner öffnen
und zweimal „Im Ordner zeigen“ meldeten nie einen Misserfolg — auch dann nicht,
wenn die Datei längst nicht mehr da war. Vier davon hatten eine Fehlermeldung,
die nie erschien; zwei schrieben nur ins Protokoll, und auch das nur so leise,
dass es dort nicht ankam.

Der Grund lag eine Ebene tiefer: Die Systemfunktion meldete „Erfolg“, sobald
sie den Öffnungsversuch abgesetzt hatte — ob etwas aufging, sah sie nie nach.
Jetzt prüft sie, ob es den Pfad überhaupt gibt, liest die Rückmeldung des
Systems aus und nennt den Grund.

## Neu: Anwendung direkt auf der PS5 installieren

Selbst gebaute Pakete scheitern auf der Konsole mit `CE-100096-6`. Das neue
Werkzeug legt die Kachel stattdessen unmittelbar an — über FTP und ein kleines
Payload, ohne Paketdatei.

Zwei Bauformen: eine Kachel, die eine Adresse öffnet (abgelesen an sechs
Kacheln, die auf einer echten Konsole liefen), und der Weg mit eigenem
Programm.

## Neu: Zweiter Sendeweg, wenn Port 9021 zu bleibt

Über den WebKit-Einstieg bleibt der Payload-Port der Konsole verschlossen,
obwohl dort ftpsrv, klogsrv und ShadowMount+ laufen. Jedes Nachladen scheiterte
dann, und die Meldung nannte nur einen abgewiesenen Port.

Ist 9021 zu, geht die Datei jetzt über den Payload Manager auf Port 8084.
Damit lässt sich einmal `elfldr` starten — danach steht 9021 offen, auch für
alles Weitere. Der Weg über einen USB-Datenträger bleibt erhalten; er trägt
auch dann noch, wenn gar kein Dienst mehr antwortet.

## Neu: Die Konsole fragen statt raten

Ab ShadowMount+ 1.7alpha13 beantwortet die Konsole über eine eigene
Schnittstelle, welche Abbilder sie kennt, was eingehängt ist und wieviel Platz
bleibt. Bisher liest das Programm das aus FTP-Verzeichnissen ab — das sieht
Dateien, nicht den Zustand. Die Anbindung liegt bereit; sie nutzt nur die
lesenden Abfragen.
