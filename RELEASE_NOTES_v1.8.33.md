# PS5 Dump & Image Converter v1.8.33 – Release Notes

## Zweck dieses Releases

Ein zweiter vollständiger Praxistest, bewusst mit **sechs anderen Backups** als beim ersten Durchgang und mit Extremen bei Dateizahl und Dateigröße:

| Backup | Größe | Dateien | warum ausgewählt |
| --- | --- | --- | --- |
| Instant Sports Plus | 2,46 GiB | 323 | Referenz |
| Wer wird Millionär | 2,62 GiB | 258 | Gedankenstrich im Titel |
| Teardown | 3,95 GiB | **5103** | Dateizahl-Extrem |
| Matchbox Driving Adventures | 5,61 GiB | 196 | `™` im Containernamen |
| The Precinct | 8,10 GiB | 819 | großer Dump |
| Double Dragon Revive | 9,91 GiB | **51** | wenige, sehr große Dateien |

Dazu vier fremde `.exfat`-Container als Eingabe. **22 Konvertierungen** über alle acht Aufgaben und alle Formatkombinationen, rund **87 GiB** Ergebnisse, Gesamtlaufzeit **3 Stunden**. Fünf Läufe scheiterten – die Ursachen sind hier behoben.

## Behobene Fehler

### 1. Die `.ffpkg`-Extraktion verlor still eine Datei

Aus einem Paket mit 196 Dateien kamen 195 heraus. Verloren ging `sce_sys/about/right.sprx` – eine Datei, die in **allen 32 Backups** der Sammlung vorkommt. Gemeldet wurde lediglich `robocopy fehlgeschlagen (rc=9)`.

Der Vergleich der drei Extraktionswege grenzte es ein:

| Weg | Dateien Quelle/Ergebnis |
| --- | --- |
| `.ffpfsc` → Ordner (PFS) | 323 / 323 |
| `.exfat` → Ordner (exFAT) | 258 / 258 |
| `.ffpkg` → Ordner (UFS2/Dokan) | **196 / 195** |

Die Datei steckte nachweislich im Paket – der Bau protokollierte „196 Dateien im UFS2-Image bestätigt", und eine Bytesuche fand den Verzeichniseintrag bei Offset `0x16BFE0020`. Verloren ging sie beim Auslesen: robocopy lief mit `/MT:8 /R:1 /W:1` gegen einen Dokan-Mount, der unter Last `ERROR_NO_SYSTEM_RESOURCES` (0x5AA) lieferte, und gab nach einem einzigen Wiederholungsversuch ein ganzes Verzeichnis auf.

Behoben durch drei Änderungen: weniger Parallelität und mehr Geduld (`/MT:4 /R:3 /W:2`), einen **Abgleich gegen die Soll-Liste** des gemounteten Abbilds statt blinden Vertrauens in den Rückgabewert, und ein einzelnes Nachholen fehlender Dateien. Bleibt danach etwas offen, nennt die Meldung die Dateien beim Namen statt einer Nummer.

### 2. Sonderzeichen im Quellnamen brachen den Packlauf ab

```
ValueError: Filename 'Matchbox™ Driving Adventures (01.000.001).exfat'
contains non-ASCII characters and cannot be stored in a PFS image
```

Folgefehler des `--no-rename-inner-image` aus v1.8.32: Der Originalname ging unverändert an mkpfs, PFS-Verzeichniseinträge speichern Namen aber als ASCII. Beide Schalterstellungen waren damit falsch – mit Umbenennung wurde der Name verstümmelt, ohne brach der Lauf ab.

Jetzt wird nur gefaltet, was ASCII nicht darstellen kann:

| Original | Innenname |
| --- | --- |
| `Matchbox™ Driving Adventures (01.000.001).exfat` | `Matchbox(TM) Driving Adventures (01.000.001).exfat` |
| `Who Wants to Be a Millionaire – New Edition (…).exfat` | `Who Wants to Be a Millionaire - New Edition (…).exfat` |
| `Instant Sports Plus (01.002.001).exfat` | unverändert |

Die Versionsklammer bleibt in jedem Fall erhalten – genau dafür war das Flag da.

### 3. Sammelkonvertierung scheiterte an einer einzigen Quelle

Drei Quellen (`.ffpfsc`, `.exfat`, `.ffpkg`) nach `.ffpfsc`: Der gesamte Auftrag wurde abgelehnt, weil die erste Quelle bereits im Zielformat vorlag. Die anderen beiden wären sauber durchgelaufen. Solche Quellen werden jetzt übersprungen und im Protokoll benannt; abgelehnt wird nur noch, wenn **keine einzige** Quelle etwas zu tun hat.

### 4. Zwei Formatkombinationen wurden angeboten, aber nicht ausgeführt

Aufgabe 6 bot `.ffpkg` → `.ffpfs` an; die Verteilung kannte den Weg nicht und brach mitten im Lauf mit „Nicht unterstützte Konvertierung" ab. Der Weg ist jetzt verdrahtet (dieselbe Einbettung wie nach `.ffpfsc`, nur ohne Kompression).

`.ffpfs` → `.ffpfsc` und umgekehrt lassen sich weiterhin nicht ausführen – dafür gibt es keinen Weg in der Engine. Statt der irreführenden Meldung „Quelle und Zielformat sind identisch" steht dort jetzt, was stattdessen zu tun ist. Ein Test stellt sicher, dass **jede angebotene Kombination** entweder verdrahtet oder erklärt ist.

### 5. Gewähltes Hintergrundbild überlebte den Neustart nicht

In der Konfiguration stand:

```
background_image_path = C:\...\Temp\_MEI213362\Hintergrundbilder\05_waves.png
```

Der Auswahldialog startet im mitgelieferten Bildordner, der in der EXE unter `sys._MEIPASS` liegt – ein Ordner, den PyInstaller beim Beenden löscht. Die Einstellung zeigte danach ins Leere, das Programm fiel still auf das Standardbild zurück.

Mitgelieferte Bilder werden jetzt als `bundled:05_waves.png` abgelegt und beim Laden neu aufgelöst. Bestehende tote Pfade werden automatisch repariert, sofern der Dateiname zu einem mitgelieferten Bild passt. Eigene Bilder außerhalb des Bündels bleiben unverändert als absoluter Pfad.

### 6. PKG-Merger übersah Split-Sätze mit Punkt im Namen

Die Namenszerlegung suchte den **ersten** Punkt statt der Dateiendung:

| Dateiname | vorher | jetzt |
| --- | --- | --- |
| `GAME_0.pkg` | erkannt | erkannt |
| `Arcade Game Zone (01.003.000)_0.pkg` | **übersehen** | erkannt |
| `Game.v1.00_0.pkg` | **übersehen** | erkannt |

Betroffen war damit ausgerechnet das Namensschema, das dieses Programm selbst vergibt.

### 7. Arbeitsordner blieben liegen

`_cleanup_exit_temp_targets()` hing ausschließlich am Schließen der Oberfläche – ein Lauf über die Kommandozeile endet über `sys.exit()` und räumte nie auf. Jede Aufgabe, die die UFS2Tool-Laufzeit auspackte, hinterließ einen Ordner mit rund 534 KiB. Der CLI-Modus räumt jetzt selbst ab, und Reste älterer Läufe (älter als 12 Stunden) verschwinden beim nächsten Start. Die Altersgrenze schützt einen parallel laufenden zweiten Vorgang.

### 8. Kleinere Korrekturen

- **Cover-Vorschau** in der Sidebar sitzt mittig statt oben klebend und seitlich um ein Pixel versetzt (gemessen vorher 96/97 links-rechts und 3/68 oben-unten, jetzt 97/97 und 24/25). Die Bildgröße bleibt unverändert.
- **Sprachwechsel** erfasst jetzt auch die Einträge im Menü WEITERE TOOLS; sie blieben bisher in der Sprache des Programmstarts stehen.
- **Pillow-Warnung** beim Start entfällt: `Image.getdata()` ist seit Pillow 12 veraltet und wird mit Pillow 14 entfernt.

## Spiel-Info während einer laufenden Konvertierung

`_on_source_path_changed` steigt bei `is_running` sofort aus – bewusst, denn eine Metadaten-Auflösung liest bei Containern mehrere Gigabyte und würde der laufenden Konvertierung Platte und CPU wegnehmen. Der Abbruch geschah aber **stillschweigend**. Ergebnis im Fenster *Spiel-Info – Updates & Patches*: keine Metadaten, keine Updates, keine Downloads – und teilweise noch Titel und Cover der zuvor gewählten Quelle, was stimmig aussah und es nicht war.

Nachgestellt:

| `is_running` | Ergebnis |
| --- | --- |
| False | `title_id='PPSA15246'`, Cover vorhanden |
| True | `title_id=''`, kein Cover |

Behoben in zwei Schritten. **Erstens** nennt das Fenster jetzt den Grund und räumt die alten Werte weg:

```
während der Aufgabe:  TITEL –  TITLE ID –  VERSION –
                      Status: „Wird nach Abschluss der laufenden Aufgabe geladen"
                      Methode: „(wartet auf das Ende der Aufgabe)"
```

**Zweitens** wird die Quelle vorgemerkt und im gemeinsamen Ausgang jeder Aufgabe – dem `finally`, das Erfolg, Fehler und Abbruch gleichermaßen durchläuft – automatisch nachgeladen, sofern sie noch die aktuelle ist:

```
nach dem Ende:  TITEL Teardown  TITLE ID PPSA15246  VERSION 01.006.000
                REGION Europa   HERSTELLER Saber Interactive, Inc
                Status: „9 Updates geladen (Online, 5.5s)" – mit Download-Einträgen
```

Wählt man zwischenzeitlich eine andere Quelle, gilt die neue; läuft direkt die nächste Aufgabe, bleibt es bei der Vormerkung.

## Bessere Title-ID, wenn die param.json fehlt oder defekt ist

Fehlt `sce_sys/param.json` oder lässt sie sich nicht als JSON lesen, bietet das Programm vor dem Bau an, eine minimale Ersatzdatei anzulegen. Die dafür nötige Titel-ID kam bisher ausschließlich aus einer Mustersuche im **Ordnernamen** – in der geprüften Sammlung trägt aber nur ein Teil der Ordner ein `PPSA…` im Namen.

Nachgemessen an `sce_sys/nptitle.dat`, einer 160 Byte großen Metadatendatei neben der `param.json`:

```
0000  4e 50 54 44 00 00 00 80 00 00 00 00 00 00 00 00   NPTD............
0010  50 50 53 41 31 38 30 38 39 5f 30 30 00 00 00 00   PPSA18089_00....
0020  ...                                               (128 Byte Signatur)
```

| | |
| --- | --- |
| Backups mit `param.json` | 32 |
| davon mit `nptitle.dat` | **32** |
| Titel-ID stimmt mit `param.json` überein | **32** |
| immer an Offset | `0x10` |

Die Reihenfolge ist jetzt: erst `nptitle.dat` (Magic `NPTD` prüfen, Suffix `_00` abschneiden, Muster validieren), dann als Notnagel der Ordnername. Weicht der Ordnername von der Datei ab, gilt die Datei.

**Nicht rekonstruierbar bleiben** die vollständige Content-ID und der Spieltitel: In `nptitle.dat` steht nur `PPSA18089_00`, nicht der Regionalpräfix und das Label. Die `eboot.bin` enthält beides ebenfalls nicht – ein Vollscan über 33 MB fand weder Titel- noch Content-ID.

## Drei wiederbelebte Werkzeuge

Beim Durchsehen fiel auf, dass vier Module in die EXE gebündelt wurden, vom Programm aus aber gar nicht erreichbar waren – sie hatten außer ihren eigenen Unittests keinen Aufrufer. Drei davon haben jetzt ein Fenster im Menü **WEITERE TOOLS**:

**SELF-Inspektor** zeigt den Aufbau einer `eboot.bin`, `.self`, `.sprx` oder `.prx`: Container-Art, eingebettetes ELF, Signaturkategorie und Segmenttabelle. Dabei mussten am Lesemodul drei Dinge korrigiert werden:

| | vorher | jetzt |
| --- | --- | --- |
| Zweite PS5-Magic `0xEEF51454` | abgewiesen | erkannt |
| Reines ELF als `eboot.bin` | Fehler | eigene Containerart |
| Lesevorgang | ganze Datei in den Speicher | max. 1 MiB Kopfbereich |

Von sechs echten `eboot.bin` liefen vorher **drei**, jetzt alle. Double Dragons `eboot.bin` ist 167 MB groß – die alte Fassung hätte sie vollständig eingelesen.

**Dump umbenennen** schlägt aus Title-ID, Titel und Version einen sprechenden Ordnernamen vor und benennt auf Wunsch um. **Debug-PKG bauen** erzeugt aus einem Dump-Ordner einen strukturell gültigen, **unsignierten** `.pkg`-Container für Struktur- und Werkzeugtests.

`dpi_upload` bleibt als Quelltext samt Tests erhalten, wandert aber nicht mehr in die EXE: Der etaHEN-Dienst, gegen den es arbeiten würde, ließ sich nie erproben.

## Aufgeräumte Titelleiste

**PKG-MERGER** und **PARAM/MANIFEST** sind von eigenen Schaltflächen ins Menü **WEITERE TOOLS** gewandert. Die Leiste trägt damit 10 statt 12 Knöpfe; das Menü umfasst sieben Einträge.

## Verifikation

- Testsuite: **292 Tests**, alle grün. Neu: `test_ufs2_extract_complete.py`, `test_kleine_fixes.py`, `test_werkzeugmenue.py`, `test_info_metadaten.py`; erweitert: `test_self_reader.py`, `test_inner_image_name.py`, `test_pkg_merger.py`, `test_same_format_conversion.py`, `test_param_json_recovery.py`.
- Projekteigene Release-Suite (Syntax, Build-Readiness, Code-Quality) und `tools/gui_smoke_test.py` grün.
- **Round-Trip bitgenau:** Ordner → `.ffpfsc` → Ordner ergibt 323 Dateien / 2 636 588 390 Bytes, SHA-256 aller Dateien identisch, null Abweichungen.
- Alle sechs `eboot.bin` im SELF-Inspektor geöffnet, Speicherspitze je 1,1 MB.
- Debug-PKG-Rundlauf: gebaut und mit dem eigenen `pkg_reader` wieder eingelesen, Content-ID stimmt überein.

## Vollständigkeit des Release

Versionen konsistent auf **v1.8.33** angehoben in `APP_VERSION`, `file_version_info.txt` (5 Felder), `PS5ImageConverter_Pro.spec`, `Build_EXE.ps1`, `Start_Build.bat`, `test_build_ready.py`, `README.md`, `BENUTZERHANDBUCH.md`, `CHANGELOG.md` und `SOURCE_FILE_MANIFEST_v1.8.33.sha256`.

Handbuch um die Kapitel 13.1 (SELF-Inspektor), 13.2 (Dump umbenennen) und 13.3 (Debug-PKG bauen) erweitert.
