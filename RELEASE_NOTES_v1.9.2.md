## Neu: die Bauform ist wählbar

Unter QUELLE steht eine neue Zeile **BAUFORM (Container)** mit zwei Möglichkeiten.

| Bauform | Aufbau | 200-MB-Quelle |
| --- | --- | --- |
| **exFAT im Container** (Vorgabe) | ein einziger Durchgang; die Engine wickelt das exFAT selbst ein und komprimiert es dabei | **1,3 s** |
| PFS im Container | erst ein rohes inneres PFS, dann der Container darum | 6,3 s |

Beide ergeben ein gültiges Abbild. Die Vorgabe ist die schnellere, weil sie sich
einen kompletten Schreibdurchgang spart.

**Eine Ausnahme gibt es:** Wer unkomprimiert baut, bekommt weiterhin den
zweistufigen Weg. Die Engine nimmt bei einem einstufigen `pack folder` den
Schalter für „nicht komprimieren" nicht an und komprimiert trotzdem. Das
Programm schaltet in diesem Fall selbst um und schreibt es ins Protokoll.

## Neu: die Infobox sagt, ob schon ein AMPR EMU drinsteckt

Die Spielangaben haben eine Zeile **AMPR EMU**. Sie beantwortet eine Frage, für
die man vorher in den Dump hineinsehen musste.

Wichtig ist dabei, was **nicht** behauptet wird: Lässt sich eine Quelle nicht
öffnen — etwa ein UFS2-basiertes `.ffpkg` —, steht dort **nicht ermittelbar**.
Ein leeres Leseergebnis wird nicht als „kein Emulator vorhanden" ausgelegt; das
wäre eine Aussage über eine Datei, in die niemand hineingesehen hat.

## Neu: „PKG bauen" auf allen Systemen

Das Werkzeug erzeugt aus einem Dump-Ordner ein `.pkg` und lag bisher nur als
Windows-Fassung bei. Es liegt jetzt für **vier** Ziele bei — Windows, Linux,
macOS (Intel) und macOS (Apple Silicon) —, und das Programm wählt den passenden
Bau anhand von Betriebssystem **und** Prozessor. Das Ausführungsrecht setzt es
außerhalb von Windows selbst; weder NTFS noch eine ZIP-Datei trägt es weiter.

## Behoben

**Aufgabe 7 vertauschte die Bauform.** Ein als exFAT-im-Container gebautes
Abbild kam nach dem Bearbeiten im AMPR-EMU-Manager als PFS-im-Container zurück
— das Bearbeiten änderte also stillschweigend den Aufbau. Der Rückbau folgt
jetzt der Form, aus der die Quelle stammt.

**Pack- und Prüfstufe fielen still auf die Vorgabe zurück.** Beide Felder halten
ihren Wert als Anzeigetext und schlagen ihn in einer Tabelle nach. Stand der Text
nicht darin, setzten sie die Vorgabe — und speicherten sie. Bei der Prüfstufe
heißt die Vorgabe „Schnell": Wer „Vollständig" gewählt hatte, bekam unter
Umständen dauerhaft die schnelle Prüfung, ohne dass die Oberfläche etwas anderes
zeigte. Ein unbekannter Text lässt die bisherige Wahl jetzt stehen und wird
protokolliert.

**Die Prüfstufen-Liste blieb beim Sprachwechsel stehen.** Die Packstufe direkt
darüber wurde übersetzt, die Prüfstufe nicht. Beide werden jetzt gleich
behandelt.

**Der Diagnosebericht zeigte die Engine-Ausgabe nicht.** Der Abschnitt mit den
letzten Protokollzeilen wurde nur aus einem der beiden Ausgabewege gefüllt.
Ausgerechnet die gebündelte Ausgabe von mkpfs und UFS2Tool — der Hauptteil jedes
Laufs — fehlte darin, und damit genau das, wofür man den Bericht aufmacht, wenn
ein Lauf an der Engine scheitert.

**Die eingestellte Schriftgröße wirkte auf dem Mac nicht.** Der Wert wurde
gelesen, aber wegen eines fehlenden Imports nie angewandt; der Fehler blieb in
einer Ausnahmebehandlung hängen. Die Einstellung greift jetzt.

**Die Vorschau packte einzeln liegende Abbilder aus,** statt sie zu lesen. Bei
200 MB dauerte das 4,97 Sekunden statt 0,12 — bei einem großen Titel
entsprechend länger.

## Neue Engine

Die PFS-Verarbeitung läuft über **MkPFS 1.0.0**. Für die neue Vorgabe-Bauform
ist das mehr als ein Versionssprung: Die Prüfliste erkennt jetzt, dass die
Spieldateien eine Ebene tiefer liegen, und meldet nicht mehr `param.json`,
`eboot.bin` und `pfs-version.dat` als fehlend, obwohl sie vorhanden sind.

Die Kompression ist fest auf `zlib-ng` gestellt. Ohne diese Festlegung wählte
die Engine selbst und bevorzugte ein Rechenwerk mit eigener Stufenskala, das bei
gleicher Einstellung andere Bytes geschrieben hätte.

## Lizenzangaben ergänzt

`UFS2Tool` ist eigenständig gebaut und trägt Microsofts .NET-8-Laufzeit in der
Programmdatei. Für die Windows-Fassung gilt dafür die .NET Library License, für
Linux und macOS die MIT-Lizenz. Das steht jetzt in `THIRD_PARTY_LICENSES.md`,
zusammen mit dem Nachweis, dass die vier Dateien mit gesonderten Bedingungen in
diesem Bau nicht enthalten sind.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.2.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.2_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.2_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.2_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.2.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün — 1897 Prüfungen in 88 Dateien —, Anzeigediagnose ohne
Auffälligkeit, Umgebungsprüfung 15/0.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.1...v1.9.2
