# PS5 Dump & Image Converter v1.8.32 – Release Notes

## Zweck dieses Releases

Alle acht Aufgaben wurden mit echten Backups in allen Formaten durchgespielt: **19 Konvertierungen**, rund **10 GB** Ergebnisse, **29 Validator-Läufe**, zwei Uploads auf die Konsole und 15 geprüfte Werkzeuge. Verwendet wurden acht verschiedene Backups (Crazy Chicken Shooter, Terminator 2D, Personality and Psychology Premium, Arkanoid Eternal Battle, Asterix & Obelix Heroes sowie Arcade Game Zone und Crazy Chicken Bundle als Container).

Diese Version enthält, was dabei aufgefallen ist – acht Punkte, alle mit Regressionstests abgesichert.

## Behobene Fehler

### 1. Kommandozeilenmodus brach an einem Pfeilzeichen ab

Leitet man die Ausgabe in eine Datei um, wählt Windows die Codepage der Konsole (meist cp1252). Die Protokollzeile „618.4 MB → ~347.6 MB" löste dort einen `UnicodeEncodeError` aus, der bis in den Aufgaben-Thread durchschlug und die Konvertierung als „Unerwarteter Fehler" beendete – **obwohl die Arbeit fertig war** („Extraction complete, Bytes written: 264830976"). Vier von neunzehn Testläufen scheiterten daran.

`_prepare_cli_streams()` stellt stdout/stderr jetzt auf UTF-8 um; zusätzlich fängt `_append_to_log()` Kodierfehler ab. Eine Protokollzeile kann eine laufende Aufgabe nicht mehr abbrechen.

### 2. Aufgabe 4 konnte eine .ffpkg nicht neu aufbauen

Die Auswahlliste bietet „.ffpkg (Neuvalidierung)" ausdrücklich an – gemeint ist das bewusste Extrahieren, Neu-Bauen und Neu-Validieren. Der Start brach mit „Quelle und Zielformat sind identisch" ab, weil die Sperre pauschal für alle Aufgaben galt, und zwar an **zwei** Stellen (Vorprüfung und Ausführung). Beide geben jetzt den Modus mit; nur Aufgabe 4 darf `.ffpkg → .ffpkg`. Nachweis: 702,8 MB in 81 Sekunden.

### 3. Validator meldete einwandfreie Backups als beschädigt

`sce_sys/pfs-version.dat` stand in der Liste der Pflichtdateien. Eine Durchsicht von 32 echten Backups zeigt: `eboot.bin` und `sce_sys/param.json` sind ausnahmslos vorhanden, `pfs-version.dat` in 30 von 32 – je nach Dumper fehlt der Marker. Zwei einwandfreie Backups galten damit als **FAILED**.

Neue Liste `RECOMMENDED_FILES`: Fehlt eine Datei daraus, gibt es eine Warnung (`recommended_missing`), keinen Fehlschlag. Die harten Kriterien bleiben unverändert.

### 4. Validator hielt zwei reguläre Containerformen für kaputt

Es gibt drei reguläre Bauformen, nicht eine:

| Quelle | Aufbau |
| --- | --- |
| Dump-Ordner | Container → rohes PFS → Spieldateien |
| `.exfat` | Container → exFAT-Abbild |
| `.ffpkg` | Container → UFS2-Abbild |

Die beiden letzten sind Absicht – Aufgabe 3 und 4 betten die Quelldatei in einem Schritt ein. Die Verschachtelungsprüfung aus v1.8.31 kannte nur die erste Form und meldete alles andere als „falsch aufgebaut", auch bereits vorhandene Container. Erkannt wird jetzt an der Signatur: exFAT-Kennung bei Offset 0x03, UFS2-Magic `0x19540119` bei 65536+1372, sonst PFS. Die tatsächlich fehlerhafte Form – eine PFS-Ebene zu viel – wird weiterhin gemeldet.

### 5. Eingebettete Abbilder bekamen verstümmelte Namen

Aus `PPSA16709 Asterix Obelix Heroes (01.000.000).ffpkg` wurde im Container `PPSA16709.000.000).ffpkg`. Ursache ist die Namensnormalisierung von mkpfs, die den Namen über `Path.suffixes` zerlegt – dort gilt bei `(01.000.000)` jeder Punktabschnitt als Endung:

```python
Path("Spiel (01.003.000).exfat").suffixes  →  ['.003', '.000)', '.exfat']
```

Alle vier `pack file`-Aufrufe geben jetzt `--no-rename-inner-image` mit; der Originalname bleibt erhalten. (Der ps5-exfat-builder hat denselben Fehler, weil er das Flag nicht setzt.)

### 6. Bibliothek zeigte für Container keine Titel

In `D:\exFAT Games` und `D:\ffpfsc Games` stand bei **jedem** Eintrag „–", weil die Metadaten im Ordner *neben* dem Container gesucht wurden – dort liegt `sce_sys/param.json` naturgemäß nie. Jetzt werden Titel, Title-ID und Version aus dem Dateinamen abgeleitet und, wenn der zugehörige Dump-Ordner daneben liegt, durch dessen echte Werte ersetzt.

| Ordner | vorher | jetzt |
| --- | --- | --- |
| Containersammlung (23 `.exfat`) | 0/23 | 23/23 |
| Containersammlung (4 `.ffpfsc`) | 0/4 | 4/4 |
| Gemischter Ordner | 32/35 | 35/35 |

### 7. Konfigurationseditor verwarf die Kommentare der Konsolendatei

`/data/shadowmount/config.ini` ist eine 146-zeilige Vorlage, in der jeder Parameter erklärt und noch keiner aktiv ist. Beim Zurückschreiben baute das Programm die Datei aus den Einträgen neu auf – daraus wären drei Zeilen geworden, die gesamte Dokumentation gelöscht.

Neue Funktion `merge_flat_ini()` bearbeitet die vorhandene Datei: Kommentare und Leerzeilen bleiben, geänderte Werte werden ersetzt, neue angehängt, entfernte **auskommentiert statt gelöscht**. An der echten Konsolendatei geprüft: 146 → 149 Zeilen, alle 124 Kommentarzeilen erhalten.

### 8. Wiederherstellen meldete einen Fehler, wenn es nichts zu tun gab

`--ampr-action ampr_restore` endete mit Exit-Code 1 und „Keine Sicherung vorhanden". Das ist der erwartete Zustand, wenn das Spiel die Bibliothek nie selbst mitbrachte. `_ampr_restore_library()` unterscheidet jetzt `restored`, `no_backup` (kein Fehler) und `failed` (echter Fehler). Der ps5-exfat-builder löst dieselbe Frage über ein Originale-ZIP und meldet dort ebenfalls keinen Fehler, wenn nichts ausgewählt wurde.

## Neu: zftpd für Übertragungen zur PS5

Der übliche FTP-Payload übertrug im Test **1,5 MB/s** – 249 MB brauchten 162 Sekunden. Der mitgelieferte `zftpd` arbeitet mit `sendfile` und sättigt laut Projektangabe eine Gigabit-Leitung.

`_ensure_zftpd()` vor jeder FTP-Verbindung:

1. Läuft zftpd bereits auf Port 2120 → wird ohne Rückfrage genutzt.
2. Sonst erscheint **eine** Ja/Nein-Frage mit dem konkreten Grund.
3. Bei „Ja" geht `zftpd-ps5-v1.5.0.elf` an den Payload-Loader (Port 9021), danach wird bis zu fünf Sekunden auf Port 2120 gewartet.
4. Bei „Nein", bei Fehlschlag oder wenn der Payload nicht startet, läuft alles wie bisher weiter. Gefragt wird nur einmal je Sitzung.

## Verifikation

- Testkampagne: 19 Konvertierungen über alle Aufgaben und Formate, alle erfolgreich (nach den Behebungen), rund 10 GB Ergebnisse.
- **Round-Trip bitgenau:** Ordner → `.ffpfsc` → Ordner ergibt 63 Dateien / 260.935.330 Bytes – identisch zum Original, auch die Namensliste.
- Konsole: zwei Backups nach `/data/homebrew` hochgeladen (mit und ohne AMPR-Bibliothek), `ampr_emu.index` mit 5728 Bytes direkt auf der PS5 gebaut.
- Werkzeuge: PKG-Merger (Erkennung und Schutzverhalten), PKG-Reader, Param/Manifest, SELF-Inspektor, Bibliothek, Diagnose, FileZilla-Erkennung sowie acht Fenster – alle in Ordnung.
- Testsuite: **100 Tests in 15 Dateien, alle grün.** Neu: `test_cli_logging.py`, `test_same_format_conversion.py`, `test_library_metadata.py`, `test_zftpd_transfer.py`, `test_inner_image_name.py`, `test_ampr_restore.py`; erweitert: `test_validator_nesting.py`, `test_ini_config.py`.

**Nicht prüfbar:** KLog, JS Loader und MicroMount brauchen laufende Payloads auf der Konsole (nur ftpsrv lief). Ein positiver PKG-Merger-Lauf fehlt, weil kein geteiltes PS5-Paket vorliegt – die Strukturprüfung lehnt PS4-Pakete korrekt ab. Der echte zftpd-Versand konnte nicht ausgeführt werden, weil kein Payload-Loader lauschte; die Entscheidungslogik ist über Tests abgedeckt.

## Vollständigkeit des Release

Versionen wurden konsistent auf **v1.8.32** angehoben in:

- `PS5ImageConverter_Pro_FINAL_revised.py` (`APP_VERSION`)
- `Build_EXE.ps1` (`$EXE_VERSION`)
- `PS5ImageConverter_Pro.spec` (Kommentar + `name=...`)
- `file_version_info.txt` (`filevers`, `prodvers`, `FileVersion`, `ProductVersion`, `OriginalFilename`)
- `Start_Build.bat` (Header/Anzeige)
- `README.md`
- `BENUTZERHANDBUCH.md`
- `test_build_ready.py` (erwarteter Output-Dateiname)
- `CHANGELOG.md`
- `SOURCE_FILE_MANIFEST_v1.8.32.sha256`

Neu im Projekt: sechs Testdateien (siehe oben).
