Ein Absturz beim Asset-Pack ist behoben, und das Programm geht sparsamer mit
Speicherplatz um – sowohl mit dem, den es selbst belegt, als auch mit dem,
den es vor dem Start prüft.

## Absturz beim Asset-Pack

In der fertigen Programmdatei brach das Bauen eines Asset-Packs bei manchen
Titeln mit einem Fenster „Unhandled exception in script" ab, zwei
Fehlermeldungen übereinander, beide `[Errno 22] Invalid argument`.

Die Programmdatei hat kein Konsolenfenster. Für das Asset-Pack ruft sie sich
selbst ein zweites Mal auf, und das Packwerkzeug schreibt seinen Fortschritt
auf eine Ausgabe, die ohne Konsole nicht existiert. Schon der erste
Fortschrittseintrag brachte es zum Absturz; die Fehlerbehandlung versuchte es
auf demselben Weg noch einmal.

Jetzt wird vor dem Start geprüft, ob die Ausgabe taugt, und falls nicht, eine
Ersatzausgabe gesetzt. Nachgestellt: ohne die Prüfung genau dieser Fehler, mit
ihr läuft der Fortschritt durch.

## Platz

### Zu wenig Platz: Meldung und Ordnerwahl

Bisher zeigte das Programm bei knappem Platz eine Warnung – und startete die
Aufgabe trotzdem. Jetzt hält es an und nennt je Ordner, was gebraucht wird,
was frei ist und was fehlt. Aus dem Dialog heraus lassen sich
**Arbeitsordner** und **Zielordner** neu wählen, danach wird neu gerechnet.
Wer sicher ist, dass Platz frei wird, kann **trotzdem starten**.

Die Schätzung richtet sich nach dem Zielformat und stützt sich auf Messungen
an einem 51-GB-Titel:

| Zielformat | Platzbedarf |
| --- | --- |
| `.ffpfsc` | 0,75 × Quellgröße |
| `.ffpfs` / `.exfat` / Dump-Ordner | 1,10 × |
| `.ffpkg` | 1,30 × |

Der Arbeitsordner wird mitgeprüft – mit AMPR EMU oder BACKPORT entsteht dort
eine vollständige Arbeitskopie. Liegen Arbeits- und Zielordner auf demselben
Laufwerk, wird die Summe geprüft. Auf der Kommandozeile entscheidet `--yes`.

### Ein fertiges .ffpkg belegte doppelt so viel Platz

Ein `.ffpkg` wird im Arbeitsordner gebaut, geprüft und dann ins Ziel gebracht.
Das war bisher immer eine vollständige Kopie – bei einem 61-GB-Paket also
zeitweise 122 GB und ein zusätzlicher Schreibdurchgang. Auf demselben
Laufwerk wird jetzt verschoben; das kostet weder Zeit noch Platz. Alle
Prüfungen danach laufen unverändert.

### Reste abgebrochener Läufe blieben liegen

Aufgeräumt wurde nur bei wenigen Aufgaben, weil das Aufräumen an einer Stelle
hing, die die meisten gar nicht durchlaufen. In einer Prüfreihe lagen dadurch
178 GB fast einen Tag im Arbeitsordner. Jetzt wird am Ende jeder Aufgabe
aufgeräumt; was jünger als zwölf Stunden ist, bleibt – das schützt Aufgaben in
einem zweiten offenen Programmfenster.

## Aufgabe 7 und ein alter Zielordner

Mit einem Dump-Ordner als Quelle blendet Aufgabe 7 das Zielfeld aus – sie
arbeitet im Ordner selbst. Beim Start wurde das ausgeblendete Feld trotzdem
geprüft: Stand darin noch ein Ordner von früher, etwa auf einem inzwischen
abgesteckten USB-Laufwerk, brach die Aufgabe mit „Zielverzeichnis existiert
nicht" ab. Das ist behoben. Der gespeicherte Ordner bleibt stehen, und mit
`.ffpfsc`, `.exfat` oder `.ffpkg` als Quelle wird das Ziel weiter geprüft.

## Oberfläche

- **BAUFORM** erscheint nur noch bei `.ffpfsc`. Bei jedem anderen Zielformat
  und bei den Aufgaben 7 und 8 hatte sie keine Wirkung.
- **Vermessen der Quelle** zeigt jetzt Fortschritt und lässt sich abbrechen.
  Bei einem 51-GB-Dump auf einer USB-Platte dauert das 37 Minuten, in denen
  bisher nichts zu sehen war und Abbrechen nicht ging.

## Knapper Arbeitsspeicher wird jetzt benannt

Brechen große Aufgaben mit `[Errno 22] Invalid argument` ab, lag das in
unseren Messungen jedes Mal an erschöpftem Arbeitsspeicher: Alle vier solchen
Abbrüche fielen in Momente mit höchstens 20 MB freiem Speicher, bei keinem der
zwölf Läufe mit mehr als 50 MB trat der Fehler auf. Dieselben Schritte liefen
mit ausreichend Speicher fehlerfrei durch.

Das Programm misst den freien Arbeitsspeicher jetzt während jeder Aufgabe mit.
Bricht sie ab und lag er zeitweise unter 100 MB, nennt die Fehlermeldung das
als vermutliche Ursache. Ohne ausreichend Messdaten – etwa wenn die
Speicherabfrage nicht verfügbar ist – wird nichts behauptet.

Hilfe: andere Programme schließen, insbesondere Browser und weitere offene
Programmfenster, und große Titel nacheinander statt gleichzeitig verarbeiten.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.15.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.15.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
