## Was ist neu

**Ein neuer Knopf: WEBKIT AUTOLOADER.**

Er steht in der Titelleiste dort, wo bisher SHADOWMOUNT+ saß, und öffnet ein
kleines rahmenloses Fenster mit drei Wegen:

| Weg | Was er tut |
| --- | --- |
| Host starten (Windows-Programm) | Täuscht der Konsole `manuals.playstation.net` vor und liefert ihr den Autoloader aus |
| Host starten (Python-Skript) | Dasselbe für Linux und macOS |
| Installer an die PS5 senden | Bringt die `.elf` auf die Konsole |

Der Host belegt DNS (UDP 53) und HTTPS (TCP 443) und braucht dafür
Administratorrechte; das Fenster sagt es vorher. Er läuft danach in einem
eigenen Fenster weiter und zeigt die Adresse an, auf die der DNS der Konsole
gestellt werden muss.

**Beim Installer entscheidet das Programm selbst, welchen Weg es nimmt.**
Lauscht ein Payload-Loader auf **Port 9021**, geht die Datei direkt dorthin.
Schweigt der Port, wird das gesagt — und die Datei kommt stattdessen per FTP
ins **Wurzelverzeichnis** eines USB-Datenträgers der Konsole. Als Port wird
2121 und danach 2021 probiert; genommen wird der erste, der antwortet.
Stecken mehrere Datenträger, wird gefragt, welcher es sein soll. Von dort
holt der **Payload Manager** der Konsole die Datei ab.

Danach liegt die Kachel **WebKit Autoload** auf dem Startbildschirm unter
**Medien**.

An echter Hardware durchgespielt: Port 9021 schwieg, 2121 antwortete, und der
Installer lag anschließend mit 2 163 968 Byte und den Rechten 0777 im
Wurzelverzeichnis von `/mnt/usb0` — genau so, wie ihn der Payload Manager
braucht.

## Eine neuere Fassung einspielen

Die drei Dateien liegen im Ordner `PS5 WebKit Autoloader` neben dem Programm.
Erscheint eine neue Fassung, genügt es, sie dort hineinzulegen: Gesucht wird
nach dem Muster `webkit-autoloader-host_v*.exe` beziehungsweise `*.py` und
`webkit-autoloader-installer_v*.elf`, genommen wird die **höchste
Versionsnummer**. Die alte Datei darf liegen bleiben. Beim nächsten Bau
wandert der Ordnerinhalt unverändert ins fertige Programm.

## Runde Ecken

Die beiden Karten im Hauptbereich haben abgerundete Ecken. Tk kennt so etwas
nicht – ein Rahmen ist immer ein Rechteck. Gelöst ist es über vier kleine
Bilder auf den Ecken, jedes aus zwei Quellen zusammengesetzt: außerhalb des
Viertelkreises der Bildausschnitt, der *hinter* der Karte liegt, innerhalb die
Kartenfläche selbst. Weil beide aus demselben Bild stammen, sitzt der Übergang
nahtlos – die Ecke sieht weggeschnitten aus, nicht überklebt.

## Einstellbar: wie stark das Bild durchscheint

Im Einstellungsfenster gibt es unter **Darstellung** sieben Schieberegler.

| Regler | Wirkung | Vorgabe |
| --- | --- | --- |
| Pfad-Karte | Bild hinter QUELLE, ZIELFORMAT und den übrigen Feldern | 40 % |
| Knopfleiste unten | Bild hinter STARTEN und ABBRECHEN | 30 % |
| Status-Log | Farbe des Protokollfelds Richtung Bildfarbe | 30 % |
| Hintergrundbild: Helligkeit / Kontrast | wirkt auch auf Karte und Leiste | 100 % |
| Seitenleiste: Helligkeit / Kontrast | davon unabhängig | 100 % |

Übernommen wird beim Loslassen des Reglers – während des Ziehens würde jedes
Zwischenbild neu gerechnet. Ein Knopf setzt alle sieben zurück; die Vorgaben
sind genau die Werte, die bis hierher fest verdrahtet waren. Wer nichts
verstellt, sieht denselben Stand wie vorher.

**Das Status-Log reagiert schwächer**, und das hat einen Grund: Es ist ein
Textfeld und damit deckend – ein Bild kann dort nicht wirklich durchscheinen.
Der Regler zieht stattdessen seine Flächenfarbe zur Farbe des Bildes hin. Bei
einem sehr dunklen Bild ist der Unterschied klein.

Nachgemessen an der mittleren Helligkeit: Die Pfad-Karte geht von 43,3 bei
0 % über 37,4 bei der Vorgabe auf 29,4 bei 100 %. Beim Hintergrundbild
wandert sie mit dem Helligkeitsregler von 7,1 über 18,9 auf 33,6, und der
Kontrastregler verändert die Streuung von 5,1 über 12,8 auf 22,2.

## Miniaturvorschau der Hintergrundbilder

Neben beiden Klapplisten steht jetzt eine kleine Vorschau des gewählten
Bildes. Sie zeigt es bereits mit Helligkeit und Kontrast – also so, wie es im
Fenster ankommt – und behält das Seitenverhältnis, statt das Motiv zu
verzerren.

## SHADOWMOUNT+ ist umgezogen

Der Konfigurationseditor sitzt nicht mehr als eigener Knopf in der
Titelleiste, sondern unter **WEITERE TOOLS**. Er kann unverändert alles, was
er vorher konnte.

## Behoben

**Das Fenster zuckte kurz nach dem Start.**

Rund eine Viertelsekunde nachdem das Fenster erschien, sprang der Inhalt
einmal: Die obere Bedienzeile rutschte 8 Pixel nach oben, und die Pfad-Karte
wurde 12 Pixel flacher.

Die Ursache lag in der Reihenfolge. Windows vergibt die endgültige
Fenstergröße erst beim Abbilden; vorher misst sich die Karte zu schmal, und
die Einbauzeile (AMPR EMU / BACKPORT) bekommt eine eigene Zeile. Sobald das
Fenster dann wirklich dasteht, meldet es seine wahre Breite, die Zeile wandert
neben die Prüfstufe und die Zeile darunter fällt zusammen — sichtbar als
Sprung, weil das Fenster zu diesem Zeitpunkt schon zu sehen war.

Nachgemessen wurde alle 40 Millisekunden: **41 Bewegungen nach dem
Sichtbarwerden, jetzt 2** — und diese zwei sind der Startbildschirm, der sich
verabschiedet. Das Ergebnis ist dasselbe wie vorher, es steht nur schon da,
bevor man hinsieht. Das Fenster erscheint dafür rund 0,4 Sekunden später.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.0.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.0_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.0_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.0_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.0.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün, Anzeigediagnose ohne Auffälligkeit, Umgebungsprüfung
15/0.

Zur Versionsnummer: Nach v1.8.100 beginnt mit **v1.9.0** eine neue Reihe.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.100...v1.9.0
