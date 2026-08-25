## Was ist neu

**Jetzt auch das ß.**

Mit v1.8.99 kamen die Umlaute; hier folgt der zweite Teil. Aus „heisst" wird
„heißt", aus „ausserhalb" „außerhalb", aus „Grösse" „Größe".

Das betrifft weniger Stellen, als man denkt: **von 194 geprüften Wörtern
brauchten 18 ein ß.** Nach kurzem Vokal bleibt es bei ss, und das ist der
häufigere Fall — „dass", „muss", „Prozess", „gemessen", „Klasse" und
„Abschluss" stehen unverändert.

| | |
| --- | --- |
| wird zu ß | groß, heißt, außen, außerhalb, schließen, ließ, weiß, Größe, Fußzeile, einschließlich |
| bleibt ss | dass, muss, Prozess, gemessen, Klasse, Abschluss, passt, erfasst, bewusst, Schlüssel |

Umgestellt sind 26 Textstellen im Programm und 54 in den Dokumenten.

Dabei kam heraus, dass ältere Changelog-Einträge noch die alte Schreibweise
trugen — auch die sind nachgezogen. Nur im Eintrag zu v1.8.99 bleibt sie
stehen: dort wird das Vorher zitiert.

## Warum wieder Wort für Wort

Eine Regel gibt es hier nicht einmal im Ansatz. „Masse" und „Maße" sind
dasselbe Wortbild mit verschiedener Bedeutung; erst der Satz entscheidet.
Und im Programm steht viel Englisches, in dem „ss" natürlich bleibt —
`Address`, `Process`, `Success`, `Message`, `Session`, `compress`.

Entschieden wurde deshalb wieder über eine geprüfte Wortliste, und angefasst
wurden nur Zeichenketten: keine Bezeichner, keine Kommentare, keine
Platzhalter, kein Code in Backticks.

Ein Beispiel für die Sorgfalt: `Schriftmasse nicht auslesbar` heißt jetzt
`Schriftmaße nicht auslesbar` — das sind Maße, keine Masse. Die
Nachbarmeldung `gemessen` bleibt dagegen unangetastet.

## Behoben

**Der Drehknopf blieb beim Designwechsel dunkel.**

Der Knopf für die Kernzahl holte seine vier Farben einmal beim Aufbau des
Fensters und behielt sie. Wer danach auf das helle oder mittlere Design
umschaltete, hatte einen dunkelblauen Knopf (#18283D) auf heller Karte
(#F1F2F3) sitzen. Am laufenden Programm nachgemessen — er folgt jetzt allen
drei Designs.

Bemerkenswert daran: Die Methode dafür gab es längst, gerufen hat sie
niemand. Derselbe Fehler war bei den runden Knöpfen schon einmal aufgetreten
und dort behoben worden; an diesem einen Bedienelement blieb er stehen.

## Aufgeräumt

Im Quelltext lag eine **1,78 MB große, vollständig ungenutzte** Kopie einer
alten MkPFS-Fassung (0.0.8) als base64-Block in einer einzigen Zeile. Das
Programm verlangt 0.0.9 und holt sie aus dem mitgelieferten Ordner; den Block
las niemand. Der Bezeichner kam im ganzen Projekt genau einmal vor — in seiner
eigenen Zuweisung.

**Die Programmdatei ist dadurch von 4,16 MB auf 2,38 MB geschrumpft — 42,9 %.**

Dazu eine Methode ohne Aufrufer, eine nie gelesene Variable, 20 ungenutzte
Importe und zwei tote Zuweisungen in Tests. Für Sie ändert sich dadurch nichts
außer der Ladezeit.

Nicht entfernt wurde, was nur *aussah* wie toter Code: `SECTOR_SIZE` war als
ungenutzt gemeldet — drei Zeilen weiter stand dieselbe Zahl als Literal. Die
Zahl hat ihren Namen zurückbekommen, statt dass die Benennung verschwindet.
Sonys Sprach- und Ländertabellen im Manifest-Modul bleiben ebenfalls: Sie
tragen Wissen, das man sich mühsam wieder zusammensuchen müsste.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.100.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.100_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.100_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.100_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.100.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün, Anzeigediagnose ohne Auffälligkeit, Umgebungsprüfung
14/0.

Zur Versionsnummer: Nach v1.8.99 kommt **v1.8.100** — die 1.8er Reihe läuft
weiter. Nachgesehen wurde vorher, dass nirgends Versionen als Zeichenketten
verglichen werden; sonst sortierte 1.8.100 vor 1.8.99. Sie wird nur angezeigt,
in den Prüfbericht geschrieben und als User-Agent gesendet.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.99...v1.8.100
