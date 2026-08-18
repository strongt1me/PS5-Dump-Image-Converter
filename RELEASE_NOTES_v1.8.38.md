# PS5 Dump & Image Converter v1.8.38 – Release Notes

## Zweck dieses Releases

Seit dem 15.08. starteten Spiele, die dieses Programm auf die Konsole geladen hat, dort nicht mehr — der Startversuch endete mit **CE-107750-0**. Aufgefallen ist es beim Praxistest des neuen Backports; die Ursache liegt aber im Übertragungsweg und betrifft **jeden** Upload.

---

## Die Ursache

Am 15.08. wurde für mehr Tempo der Payload **zftpd** (Port 2120) bevorzugt. Er arbeitet mit Zero-Copy und überträgt schneller — legt aber jede Datei **ohne Ausführungsrecht** ab.

Direkt an der Konsole nachgemessen: dieselbe 64-Byte-Datei, derselbe Zielordner, nur ein anderer Dienst.

| Payload | Port | `unix.mode` danach |
| --- | --- | --- |
| ftpsrv 1.15-ng | 2121 | **0777** |
| zftpd 1.5.0 | 2120 | **0666** |

Die PS5 startet nichts, was nicht ausführbar ist, und nennt als Grund ausschließlich `CE-107750-0`. Der Bestand auf der Testkonsole bestätigte das Muster lückenlos:

| Eintrag | Rechte | Hochgeladen | Startet |
| --- | --- | --- | --- |
| `Matchbox….exfat` | 0777 | 14.08. | ✅ |
| `Arcade_Game_Zone.ffpfsc` | 0777 | 15.08. 07:27 | ✅ |
| `KampagneMitAMPR/eboot.bin` | 0777 | 15.08. 16:10 | ✅ |
| `Terminator2D/eboot.bin` | 0666 | 16.08. | ❌ |

Die Trennlinie liegt bei **15.08. gegen 16:13** — genau dort wurde von ftpsrv auf zftpd umgestellt.

**Nachträglich reparieren lässt es sich über zftpd nicht.** `SITE HELP` meldet dort „SITE command not supported", `SITE CHMOD` wird trotzdem mit „200 CHMOD command successful" quittiert — und ändert nichts. Auch die `COPY`-Erweiterung hilft nicht.

---

## Was sich ändert

- **ftpsrv auf Port 2121 hat wieder Vorrang.** Läuft er nicht, wird wie gewohnt einmal je Sitzung angeboten, den mitgelieferten Payload zu senden. Mitgeliefert und voreingestellt ist `ftpsrv-ps5_v1.16-ng.elf`.
- **zftpd wird nicht mehr angeboten** und steht in der Suchreihenfolge ganz hinten (`2121, 1337, 21, 2120`). Wer ausschließlich zftpd laufen hat, bekommt weiterhin eine Verbindung — und dazu die neue Warnung.
- **Neu: Rechteprüfung nach jedem Upload.** Ist eine übertragene Datei nicht ausführbar, steht das sofort im Protokoll, samt Hinweis auf die Ursache. Genau dieses Schweigen hat den Fehler tagelang verdeckt.

Der Payload zftpd bleibt beigelegt und in den Credits genannt — er ist für reine Datenübertragung weiterhin brauchbar, nur eben nicht für Spiele, die anschließend starten sollen.

---

## Prüfung

| Prüfung | Umfang | Ergebnis |
| --- | --- | --- |
| Neue Tests `test_ftpsrv_transfer.py` | 21 | grün |
| Gesamte Testsuite | 436 | grün (2 übersprungen) |
| Messung an der Konsole | 2 Payloads | 0777 gegen 0666 bestätigt |

`test_zftpd_transfer.py` ist entfallen und durch `test_ftpsrv_transfer.py` ersetzt. Neu darin sind unter anderem:

- Ein laufendes zftpd allein genügt **nicht** mehr — nach ftpsrv wird trotzdem gefragt.
- Die Portreihenfolge wird festgehalten: 2121 zuerst, 2120 zuletzt.
- Die Rechteprüfung wird gegen `MLST` **und** gegen die `LIST`-Zeile geprüft, einschließlich des Falls, dass sich die Rechte nicht ermitteln lassen — dann wird bewusst nicht gewarnt, statt fälschlich Alarm zu schlagen.

---

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `PS5ImageConverter_Pro_FINAL_revised.py` | `_ensure_zftpd` → `_ensure_ftpsrv`, Portreihenfolge, Rechteprüfung nach Upload |
| `ps5_validator/utils/i18n.py` | 7 `zftpd.*`-Texte durch 8 `ftpsrv.*`-Texte ersetzt, Warnung ergänzt |
| `test_ftpsrv_transfer.py` | **neu** – 21 Tests |
| `test_zftpd_transfer.py` | entfallen |
