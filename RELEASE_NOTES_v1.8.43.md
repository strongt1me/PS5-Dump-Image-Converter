# PS5 Dump & Image Converter v1.8.43 – Release Notes

## Zweck dieses Releases

Diese Version entstand aus einem vollständigen Praxistest: alle acht Aufgaben, alle Formatkombinationen, zwei verschiedene Sicherungen, Upload auf die Konsole und sämtliche Werkzeuge. Was dabei auffiel, ist behoben – dazu drei Wünsche, die während des Tests dazukamen.

---

## PS5-Verbindung an einer Stelle

Die Adresse der Konsole lag bisher in **vier getrennten Schlüsseln**: `klog_ip` für KLOG, `<prefix>_ftp_ip` für ShadowMount+/MicroMount, `ps5_ip` für den AMPR Picker – und im JS Loader stand sie fest im Quelltext. Beim Umzug der Konsole musste man sie an vier Stellen nachtragen.

Die EINSTELLUNGEN führen sie jetzt zusammen:

| Feld | Standard |
| --- | --- |
| IP-Adresse | leer |
| FTP-Port | 2121 |
| KLOG-Port | 3232 |

Gespeichert wird beim Druck auf **Speichern**. Unbrauchbare Eingaben (Port 0, 70000, Buchstaben) werden abgefangen; das Fenster bleibt dann offen, damit nichts unbemerkt verlorengeht.

Die Fenster nehmen diese Werte als Vorschlag. **Ein Fenster mit eigenem Eintrag behält seinen** – nur wo nichts steht, greift der zentrale Wert.

### Ports passen sich selbst an

`_ps5_port_finden()` probiert **immer zuerst den eingestellten Port** und danach die für das Werkzeug bekannten:

| Werkzeug | Kandidaten |
| --- | --- |
| FTP | 2121 (ftpsrv), 1337 (etaHEN), 21 (klassisch), 2120 (zftpd) |
| KLOG | 3232 |

Antwortet ein anderer, wird er genommen, im Fenster nachgetragen und gemerkt. Antwortet keiner, bleibt der eingestellte stehen – die Fehlermeldung nennt dann den Port, den der Nutzer eingetragen hat, und nicht irgendeinen ausprobierten.

Der Knopf **Verbindung testen** sagt es direkt: „Erreichbar über Port 2121 statt 21."

---

## KLOG prüft, bevor es öffnet

Ohne laufenden klogsrv öffnete sich bisher ein Fenster, das keine Verbindung bekam. Der Knopf prüft jetzt in drei Stufen:

1. **klogsrv antwortet** → Fenster wie bisher, keine Rückfrage.
2. **klogsrv still, Payload-Loader (9021) antwortet** → Angebot, `klogsrv-ps5_v0.9.elf` dorthin zu senden.
3. **beide still** → Angebot, den Payload per FTP auf einen USB-Datenträger der Konsole zu legen.

Die Prüfung ist gekapselt: Sie kann das Fenster nie verhindern, sie ist eine Hilfe, kein Tor.

### Der Weg über den USB-Datenträger

Gibt es auf dem Datenträger `ps5_autoloader/autoload.txt`, wandert der Payload dorthin und wird eingetragen – unter dem letzten Eintrag zuerst die Pause `!2000`, darunter der Dateiname:

```
etaHEN.elf
!3000
ftpsrv-ps5_v1.15-ng.elf
!2000                        <- neu
klogsrv-ps5_v0.9.elf         <- neu
```

Bei leerer Datei genügt der Name allein. Steht er schon drin, wird nur die Datei ersetzt – kein Doppeleintrag, auch bei abweichender Groß-/Kleinschreibung. Gibt es keinen `ps5_autoloader`, wird das Wurzelverzeichnis angeboten; das passt für den Payload Manager.

**Nur wirklich eingehängte Datenträger werden angeboten.** Die PS5 hält `usb0`…`usb7` und `ext0` ständig als leere Einhängepunkte bereit. An der Konsole gemessen:

```
drwxrwxrwx 1 ... 32768 usb0     <- Stick steckt
dr-xr-xr-x 2 ...     0 usb1     <- leerer Haken
drwxrwx--- 2 ...     0 ext0     <- leerer Haken
```

Geprüft werden Schreibrecht **und** Größe – sonst stünden drei tote Einträge zur Auswahl.

---

## Bibliothek

| Vorher | Jetzt |
| --- | --- |
| kein Rollbalken | senkrecht und waagerecht |
| Titel und Pfade abgeschnitten | breitere Spalten mit Mindestbreite, Titel und Pfad wachsen mit |
| im kleinen Fenster keine Knöpfe sichtbar | Knopfleiste zuerst gepackt, immer sichtbar |
| Detailfeld nahm ein Drittel der Breite | feste 300 px, der Rest gehört der Liste |
| keine Sortierung | Klick auf die Überschrift sortiert, erneuter Klick dreht um |
| gleichförmige Zeilen | Zebrastreifen |

Die fehlende Knopfleiste hatte dieselbe Ursache wie schon einmal in v1.8.37: `btn_row.pack()` stand **nach** dem mitwachsenden Bereich.

---

## Protokollfeld und Fortschritt

**Das Protokollfeld lief mit Balkenzeilen voll.** Die Engines aktualisieren ihren Fortschritt viele Male je Sekunde; der Leser der Unterprozess-Ausgabe behandelt das `\r` bereits als Zeilenende, und die fertigen Zeilen wurden einzeln angehängt. Beim Rollen blieb oben eine angeschnittene Zeile stehen. Aufeinanderfolgende Balkenzeilen werden jetzt zu ihrer letzten zusammengefasst, die Ansicht rastet oben auf einen Zeilenanfang ein, und das Feld hat eine Obergrenze von 4000 Zeilen, aus der nur ganze Zeilen entfernt werden.

**Die Fortschrittsanzeige stand still.** Jedes `engine_pct >= 100` galt als „Finalisierung" und spulte auf 99 % des Schrittbereichs vor. mkpfs meldet aber schon `100% read`, wenn nur das *Lesen* fertig ist – das Schreiben des Abbilds folgt erst. Bei Schritt 1 (Bereich 0–60) landete die Anzeige damit auf 59,4 und stand dort, weil der Dateimonitor nur vorwärts darf und keinen Platz mehr hatte. `scan` und `read` sind jetzt ausgenommen.

An der Oberfläche nachgemessen, 249-MB-Quelle:

| | vorher | nachher |
| --- | --- | --- |
| längster Stillstand | 8,4 s bei 59,4 % | **3,0 s** |
| verschiedene Werte | 60 | **130** |
| Rücksprünge | 0 | 0 |
| Endwert | 100 % | 100 % |

Die Erklärtexte zu den Hintergrundbildern sind von 613 auf 180 und von 396 auf 157 Zeichen gekürzt.

---

## Tests

Neu sind `test_ps5_verbindung.py` (23 Fälle) und `test_klog_payload.py` (20 Fälle). Zusammen **45 Testdateien grün**.

Die USB-Erkennung wird gegen die **echten Listenzeilen der Konsole** geprüft, nicht gegen erfundene.

### Was die Kampagne gezeigt hat

- **37 Konvertierungsläufe** über zwei Sicherungen (249 MB / 63 Dateien und 618 MB / 191 Dateien) in allen Formatkombinationen der Aufgaben 1 bis 6
- **Rundlauf bitgleich**: über `.ffpfsc`, `.exfat` und `.ffpkg` kommen jeweils exakt dieselben Dateien mit identischen SHA-256 zurück – dateiweise geprüft, nicht nur über die Größe
- Ein einziger Fehlschlag, und der ist richtig: `.ffpfsc → .ffpfs` ist die bekannte Grenze; die Sammelkonvertierung meldet „2/3 erfolgreich verifiziert" und macht mit den übrigen weiter
- **Aufgabe 7** in allen fünf Aktionen, inklusive FTP-Index direkt auf der Konsole
- **Upload auf die PS5** mit und ohne AMPR EMU, jeweils per SHA-256 zurückgelesen; `eboot.bin` trägt das Ausführungsrecht (`-rwxrwxrwx`), an dem v1.8.38 gescheitert war
- **17 Werkzeugfenster** geöffnet, alle bauen sich fehlerfrei auf, kein Knopf außerhalb des sichtbaren Bereichs

---

## Dateien

| Datei | Bedeutung |
| --- | --- |
| `dist\PS5_Dump_Image_Converter_v1.8.43.exe` | Ausführbares Programm |
| `SOURCE_FILE_MANIFEST_v1.8.43.sha256` | Prüfsummen aller Quelldateien |
| `test_ps5_verbindung.py`, `test_klog_payload.py` | neue Tests |
| `BENUTZERHANDBUCH.html` / `.pdf` | Handbuch |
