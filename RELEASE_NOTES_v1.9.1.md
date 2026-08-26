## Behoben

**Der Validator sagte „fehlgeschlagen", wo er nur nicht prüfen konnte.**

Aufgabe 8 prüft ein `.ffpkg` über UFS2Tool. Das Werkzeug braucht dafür
Administratorrechte — fehlen sie, kommt es an das Abbild gar nicht heran
(`WinError 740`). Bisher landete dieser Fall bei **FEHLGESCHLAGEN**, und ein
völlig einwandfreies Abbild las sich wie ein beschädigtes.

Dafür gibt es jetzt einen eigenen Status:

| Status | Bedeutung |
| --- | --- |
| BESTANDEN | Es wurde nachgesehen, und es war nichts zu beanstanden |
| FEHLGESCHLAGEN | Es wurde nachgesehen, und es **wurde** etwas gefunden |
| **UNGEPRÜFT** | Es wurde **nichts angesehen** — kein Urteil über die Datei |

Der Bericht sagt im Klartext, was los ist und was zu tun wäre: „Die Prüfung
konnte nicht stattfinden – das ist **kein** Urteil über die Datei. Meist
fehlen Administratorrechte; dann das Programm als Administrator starten und
erneut prüfen."

Am selben `.ffpkg` (702,8 MB) nachgemessen: vorher `FAILED`, jetzt `SKIPPED`
mit dem Befund „UFS2Tool braucht Administratorrechte – die Struktur wurde
nicht geprüft".

## Für Skripte: ein eigener Rückgabewert

Im Kommandozeilenmodus gibt Aufgabe 8 in diesem Fall **4** zurück, nicht 0
und nicht 1. Beides wäre eine falsche Aussage: Eine 0 ließe ein Skript
glauben, das Abbild sei in Ordnung befunden worden, eine 1 würde es als
beanstandet melden. Vorher kam hier eine 1.

## Was sich dabei nicht ändert

**Ein gefälltes Urteil wird nicht überschrieben.** Wer schon etwas gefunden
hat, hat auch etwas gesehen — ein später auftretender Rechtefehler darf einen
erkannten Schaden nicht verdecken. `FEHLGESCHLAGEN`, `BESCHÄDIGT` und
`FEHLT` bleiben also stehen; nur eine bloße Warnung darf weichen.

**Nur echte Rechtefehler zählen.** Ein fehlendes UFS2Tool, eine unbrauchbare
Befehlszeile oder ein anderer Windows-Fehler bleiben ein Fehlschlag. Sonst
hätte man den einen Irrtum durch den anderen ersetzt — dafür gibt es einen
eigenen Gegentest.

## PKG-Merger: nicht mehr ungeprüft

Die Zusammenführung geteilter `.pkg`-Dateien war bisher nur mit **einem**
nummerierten Teil abgedeckt — das prüft die Verkettung, nicht die
Reihenfolge. Fünf Prüfungen mehr machen jetzt den Rundlauf: ein gültiges
Paket bauen, in mehrere Teile zerlegen, wieder zusammenfügen und byteweise
mit dem Original vergleichen.

Mitgeprüft ist die eigentliche Falle: **`_10` gehört hinter `_9`** — nach
Namen sortiert stünde es vor `_2`. Dazu der Satz ohne Metadatenteil, das
fehlende Mittelteil und ein Metadatenteil mit falschem Kopf.

An echten Daten gegengeprüft: An einem echten Wurzelteil einer
PS5-Aktualisierung (4 GiB) stimmt die Kopfauswertung — FIH-Kennung, Retail,
Formatversion 3, und der Subcontainer-Offset passt exakt zur Summe aus
Offset und Größe. Der Satz ist unvollständig, und genau das meldet die
Prüfung: 89,3 GiB fehlen.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.1.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.1_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.1_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.1_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.1.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün, Anzeigediagnose ohne Auffälligkeit, Umgebungsprüfung
15/0.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.0...v1.9.1
