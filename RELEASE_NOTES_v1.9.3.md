## Das Fenster merkt sich seine Größe

Bis v1.9.2 startete das Programm **immer** maximiert. Auf einem großen
Bildschirm hieß das: bei jedem Start von Hand an der Ecke kleiner ziehen.

Jetzt kommt es in der Größe und an dem Ort zurück, wo Sie es verlassen haben —
und maximiert, wenn es maximiert war. Die Maximierung wird dabei als eigener
Zustand gemerkt, nicht als Größenangabe: Sonst stünde ein auf 3440 Pixel
maximiertes Fenster später unverändert auf einem Bildschirm mit 1920.

**Drei Fälle, in denen ein gemerkter Wert nicht gilt:**

| Fall | Verhalten |
| --- | --- |
| kleiner als das Mindestmaß | wird angehoben |
| größer als der Bildschirm | wird begrenzt |
| Ort außerhalb des Bildschirms | Fenster rückt in die Mitte |

Der dritte ist der wichtigste. Wird ein zweiter Bildschirm abgezogen, liegt der
gemerkte Ort im Nichts — ohne diese Korrektur startete das Fenster unsichtbar,
und es gäbe kein Mittel, es zurückzuholen. Etwas Überstand nach links oder
rechts bleibt erlaubt; wer sein Fenster halb über den Rand schiebt, will das so.

Beim ersten Start ändert sich nichts.

## Das Handbuch erklärt, wofür jede Aufgabe gut ist

Vor jeder der acht Aufgaben steht jetzt ein Kasten **„Wofür ist das gut?"**.
Bisher stand dort, wie man eine Aufgabe bedient — aber nicht, wozu man sie
braucht und wann nicht.

Zwei Stellen waren besonders dünn:

**Aufgabe 6 (AIO)** unterschied sich für den Leser nicht erkennbar von den
Einzelaufgaben. Der Unterschied ist genau einer: Sie müssen nicht wissen, was
Sie vor sich haben — Aufgabe 6 erkennt die Quelle selbst.

**Aufgabe 7 (AMPR EMU Manager)** begann mit der Versionsgeschichte der
Oberfläche, bevor irgendwo stand, was ein AMPR EMU überhaupt ist. Das steht
jetzt zuerst: Die PS5 fragt beim Start ihren APR-Dateiresolver, wo die
Spieldateien liegen; läuft das Spiel aus einem eingehängten Abbild, bekommt er
darauf keine brauchbare Antwort.

HTML und PDF sind beide neu erzeugt.

## PS5-Pakete lassen sich lesen

Neu ist `prosperopkg read`. Es liest den **äußeren Container** einer
PS5-`.pkg`: Art des Pakets, Content-ID und die Eintragstabelle — sowohl aus
einem reinen Metadaten-Container als auch aus einem finalisierten Abbild.

An echten Dateien nachgemessen:

| Datei | Erkannt als | Befund |
| --- | --- | --- |
| ein Metadaten-Paket | `Meta` | Content-ID, 23 Einträge, davon 14 mit Namen |
| ein finalisiertes Abbild | `FullDebug` | Formatversion 3, Versätze der eingebetteten PFS |
| eine beliebige `.exe` | — | sauber als „keine PS5-PKG" abgewiesen |

Endet eine Datei früher, als ihr Kopf ankündigt — der übliche Fall bei einem
geteilten Satz —, wird gesagt, wie viele Bytes fehlen. Das trennt „unvollständig"
von „beschädigt".

**Was dabei nicht geht:** Der eigentliche Spielinhalt bleibt verschlüsselt;
dafür bräuchte es Schlüssel, die hier niemand hat. Das Programm sagt das
ausdrücklich, statt eine leere Liste zu zeigen. Die gelesenen Einträge sind die
des Pakets — `param.sfo`, `playgo-chunk.dat`, Bilder —, nicht die Dateien des
Spiels.

Das Werkzeug lag schon bisher für alle vier Plattformen bei; es fehlte nur der
Weg hinein.

## Behoben

**Spiele in Unterordnern des USB-Sticks wurden übersehen.**

Die Suche auf der Konsole kannte `usb0` bis `usb3` und keine Unterordner —
ein Stand, der fünf ShadowMount+-Fassungen zurücklag. Da die Suche nur
Verzeichnisse mit einer Spielkennung behält, fiel ein Ordner namens `homebrew`
durch das Raster: Wer sein Spiel in `/mnt/usb0/homebrew` liegen hatte, fand es
über das Programm nicht wieder, obwohl die Konsole selbst es längst findet.

Jetzt werden alle 32 Orte durchsucht, die ShadowMount+ kennt — `usb0` bis
`usb7`, jeweils auch `homebrew` und `etaHEN/games`.

**Eine ungültige Escapefolge im Quelltext.** Der Hinweis auf
`%APPDATA%\PS5ImageConverterPro` stand in einem Text, in dem `\P` keine
gültige Folge ist. Heute eine Warnung beim Bauen, in künftigen
Python-Fassungen ein Fehler.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.3.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.3_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.3_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.3_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.3.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün — 1925 Prüfungen in 90 Dateien —, Anzeigediagnose ohne
Auffälligkeit, Umgebungsprüfung 15/0.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.2...v1.9.3
