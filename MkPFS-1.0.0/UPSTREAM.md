# MkPFS 1.0.0 – eingebetteter Quellauszug

Grundlage ist **MkPFS 1.0.0** von PSBrew (<https://github.com/PSBrew/MkPFS>),
lizenziert unter GPL-3.0. Sie ersetzt seit dem 01.09.2026 die vorher hier
liegende Fassung 0.0.9.

**Die Versionsnummer taugt nicht zum Vergleichen.** Die Vorlage wird unter
derselben Nummer weitergepflegt: Der hier am 01.09.2026 zuerst eingebettete
Stand und der am 03.09.2026 nachgezogene melden beide `1.0.0`, sind aber
verschieden. Verlässlich ist ein Prüfsummenvergleich – oder die Frage, ob
`mkpfs/game_metadata.py` vorhanden ist; die Datei kam mit dem Stand vom 03.09.
hinzu.

Was der neuere Stand bringt, hier gemessen am 03.09.2026:

| | |
| --- | --- |
| `pfs.py` | `_pfs_wraps_single_exfat()` – erkennt, dass ein PFS nur eine innere exFAT-Nutzlast trägt, und lässt die PS5-Prüfliste dann aus. Ohne das meldete `verify_pfs_image` für jeden Container der Bauform **exFAT-in-PFS** drei Warnungen („sce_sys/param.json not found“, „eboot.bin not found“, „sce_sys/pfs-version.dat not found“) für Dateien, die sehr wohl da sind – eine Ebene tiefer. Da diese Bauform die Vorgabe ist, träfe es sonst jeden so gebauten Container. |
| `batch.py` | erkennt `.ffpfs` und `.ffpfsc` beim Sammelscan, vorher nur `.exfat` und `.ffpkg`. Das Programm benutzt den Sammelscan der Engine nicht; es hat mit Aufgabe 5 einen eigenen. |
| `cli.py` | `tree` läuft jetzt auch über einen Quellordner, nicht nur über ein Abbild. Der einzige `tree`-Aufruf des Programms übergibt einen Container. |
| `game_metadata.py` | neues Modul, von keinem anderen Engine-Modul importiert – **vom Programm aber sehr wohl benutzt.** `read_game_metadata()` liefert der Infobox Titel, Content-ID, Fassung, Region, Cover und den AMPR-Marker in einem Aufruf. Es greift nur bei exFAT-basierten Dateien; für alles andere – etwa ein UFS2-`.ffpkg` – bleibt die eigene Kette (`abbild_metadaten.py`) zuständig. Ein leeres Ergebnis ist dort kein Nein. |

**Was die Korrektur NICHT deckt** (gemessen, für den Entwickler der Engine
vorgemerkt): Ein Container der Bauform **PFS-in-PFS** bekommt dieselben drei
Warnungen weiterhin, auch aus vollständiger Quelle. Der äußere PFS trägt dort
einen inneren *PFS* statt eines exFAT, und `_pfs_wraps_single_exfat()` prüft
nur auf die exFAT-Signatur. Beide Container tragen genau einen Datei-Inode –
die Anzahl unterscheidet sie also nicht.

## Was hier liegt

Das Python-Paket `mkpfs/` – 16 Dateien, byte-gleich zur Vorlage bis auf die
vier unten genannten Stellen. Das Programm legt beim Start das
**übergeordnete** Verzeichnis auf `sys.path`; `import mkpfs` findet die Engine
dann von selbst.

Dazu `LICENSE` – der GPL-3.0-Text der Vorlage, unverändert. Er bleibt beim
Quellcode, den er deckt; die Nennung in `THIRD_PARTY_LICENSES.md` sagt, wozu
die Engine im Programm dient, ersetzt den Lizenztext aber nicht. Bis zum
03.09.2026 fehlte er hier als einziger unter allen eingebetteten
Fremdkomponenten.

## Der Testbestand der Vorlage liegt daneben

Unter `tests/` liegen **vierzehn** der siebzehn Testdateien des Autors samt
`fixtures/tiny.exfat.gz`. Sie laufen im Vollauf mit – die Brücke dazu ist
`test_mkpfs_vorlage.py` im Wurzelverzeichnis.

**Wozu.** Bis zum 06.09.2026 ließ sich nicht prüfen, ob eine der Änderungen
hier etwas bricht, das der Autor absichtlich so gebaut hat. Beim nächsten
Umstieg auf eine neuere Vorlage zeigen diese Tests sofort, was sich geändert
hat – die Versionsnummer taugt dafür nicht, sie bleibt `1.0.0`.

**Erste Messung am 06.09.2026:** 459 Prüfungen, eine ausgelassen, ein
bekannter Fehlschlag. Alle Änderungen dieses Projekts gehen durch.

Der ausgelassene ist `test_cli.TestCliBatchRun.test_batch_nonexistent_source_gives_clean_error`.
Er vergleicht einen selbst erzeugten Temp-Pfad mit dem Pfad in einer
Fehlermeldung; unter Windows steht in dem einen der 8.3-Kurzname
(`JBUSER~1`), im anderen der ausgeschriebene. **Gemessen: Er fällt genauso
mit der unveränderten Vorlage** – es ist die Umgebung, nicht unsere Fassung.

**Drei Dateien fehlen** (`test_compression_backends.py`,
`test_compression_integration.py`, `test_gather.py`): Sie verlangen `pytest`,
und der Testbestand dieses Projekts kommt ohne aus. Die Ecke, die sie
abdecken, bewacht hier bereits `test_mkpfs_fassung.py`.

## Was bewusst fehlt

- `mkpfs/gui/` – die mitgelieferte Oberfläche (18 Dateien, am 08.09.2026
  gegen das Quellarchiv gezählt). Sie verlangt
  `customtkinter` und `Pillow`; der PS5 Dump & Image Converter bringt sein
  eigenes Fenster mit. Dieselbe Entscheidung wie bei PS4 FFPFSC, siehe
  `PS4FFPFSC-0.2.9/UPSTREAM.md`.
- `tests/`, `.github/`, `assets/`, `scripts/` und die Baudateien der Vorlage.
  Sie gehören zum Entwicklungsstand des Werkzeugs, nicht zu seiner Ausführung.

## Nicht zu verwechseln mit `PS4FFPFSC-0.2.9/mkpfs_1_0_0/`

Daneben liegt eine **zweite** 1.0.0 – die, welche PS4 FFPFSC 0.2.8 mitliefert,
samt dessen Patch. Die beiden sind nicht dasselbe:

| | `MkPFS-1.0.0/` (hier) | `PS4FFPFSC-0.2.9/mkpfs_1_0_0/` |
| --- | --- | --- |
| Herkunft | PSBrew, Stand 03.09.2026 | Beilage von PS4 FFPFSC 0.2.8 |
| `fold_inner_name_to_ascii` | ja | nein |
| `game_metadata.py` | ja | nein |
| `_pfs_wraps_single_exfat` | ja | nein |
| Fortschritt `PS4FFPSC_PROGRESS` | nein | ja (`pbar.py`) |
| wird benutzt von | dem Programm selbst | nur dem PS4-Weg (`--ps4-mkpfs`) |

Die PS4-Fassung heißt deshalb `mkpfs_1_0_0` mit Unterstrichen: Das Programm
und sein Validator suchen ihre Engine über das Muster `MkPFS-*` und würden
sonst die falsche erwischen.

## Geänderte Zeilen

**Sieben Stellen**, jede in einem eigenen Abschnitt unten. Alle sieben sind
Zutaten dieses Projekts und **müssen bei jedem Fassungswechsel erneut
nachgetragen werden** – am 03.09.2026 haben sie den Austausch überstanden,
weil vorher nachgesehen wurde, nicht von selbst.

Bis zum 08.09.2026 stand hier „zwei Stellen“. Ein Abgleich unserer Fassung
gegen das Quellarchiv `mkpfs-1.0.0.tar.gz` ergab **vier** abweichende
Dateien; die beiden zuletzt hinzugekommenen waren nie eingetragen worden.
Verlorengehen konnten sie trotzdem nicht – jede der vier hat ihren Wächter,
und der Abgleich lief nur deshalb, weil das Archiv gerade zur Hand war. Wer
die Fassung wechselt, prüft die Liste hier **und** lässt die genannten Tests
laufen; keins von beidem ersetzt das andere.

| Datei | Zutat | Wächter |
| --- | --- | --- |
| `mkpfs/compression.py` | `_ensure_backend_with_fallback()` | `test_mkpfs_fassung.py` |
| `mkpfs/pfs.py` | `fold_inner_name_to_ascii()` | `test_mkpfs_fassung.py`, `test_inner_image_name.py` |
| `mkpfs/exfat_writer.py` | `ExfatBuildError`, Abweisung von Symlinks und Nicht-ASCII-Namen | `test_mac_befunde.py` |
| `mkpfs/cli.py` | `--verify-structure` wirkt auch im exFAT-Zweig | `test_mac_befunde.py` |
| `mkpfs/pfs.py` | Aufräumen fängt `OSError` statt nur `FileNotFoundError` | `test_mkpfs_aufraeumen.py` |
| `mkpfs/pfs.py` | `progress` für `inspect_pfs_image()` und `verify_pfs_image()` | `test_mkpfs_pruefung_exfat.py` |
| `mkpfs/cli.py` | Strukturprüfung nach `pack file` ohne Kopie der Quelle, wo kein Link geht | `test_mkpfs_pruefung_exfat.py` |

Nicht abweichend, sondern **weggelassen**: der ganze Ordner `mkpfs/gui/`
(18 Dateien). Dieses Projekt bringt seine eigene Oberfläche mit; siehe
„Was bewusst fehlt“.

### Aufräumen fängt `OSError` in `mkpfs/pfs.py`

Die Vorlage räumt ihre Zwischendateien in `except`-Blöcken weg und reicht die
ursprüngliche Ausnahme danach weiter. Ihr eigener Kommentar sagt, worum es
geht:

> Re-raise the original exception after removing the temp file so callers
> observe the original traceback.

Abgesichert war das Aufräumen mit `suppress(FileNotFoundError)`. Unter Windows
ist aber nicht „Datei weg“ der Normalfall, sondern **„Datei noch belegt“**:
`PermissionError: [WinError 32]`, ausgelöst von einem Virenscanner, dem
Indexdienst oder einem Handle, das das Betriebssystem noch nicht freigegeben
hat. Der wird von `suppress(FileNotFoundError)` nicht gefangen – er ersetzt
die Ausnahme, die eigentlich weitergereicht werden sollte.

Am 10.09.2026 in Aufgabe 3 gemessen. Der Anwender sah:

    PermissionError: [WinError 32] Der Prozess kann nicht auf die Datei
    zugreifen, da sie von einem anderen Prozess verwendet wird

Die tatsächliche Ursache – ein `RuntimeError` aus `multiprocessing` – stand
nur noch als „During handling of the above exception“ im Stapel und ging in
der Ausgabe unter. Genau der Fall, für den der Kommentar der Vorlage steht.

Betroffen sind **sieben** Stellen, `FileNotFoundError` überall durch `OSError`
ersetzt – es ist dessen Oberklasse, der bisherige Fall bleibt also gedeckt.
Eine misslungene Aufräumung hinterlässt jetzt höchstens eine Datei im
Temp-Ordner; sie bestimmt nicht mehr, was der Anwender als Fehler zu sehen
bekommt.

### `_ensure_backend_with_fallback()` in `mkpfs/compression.py`

Die Vorlage lädt in `compress_block()` und `decompress_block()` das
voreingestellte Backend über `set_backend(_backend_name)` – und bricht mit
`ImportError` ab, wenn `zlib_ng` auf dem Rechner fehlt. MkPFS 0.0.9 hatte an
dieser Stelle (oben in `pfs.py`) noch einen Rückfall auf das Standard-`zlib`
der Python-Auslieferung; der ist beim Umbau auf das neue `compression`-Modul
weggefallen.

Die neue Hilfsfunktion stellt ihn wieder her: `zlib` schreibt denselben
Datenstrom, nur langsamer. Bewusst **nicht** über das vorhandene
`init_worker()` – dessen Kette beginnt bei `isal`, das mit einer eigenen
Stufenskala arbeitet (1–9 wird auf 0–3 abgebildet) und damit andere Bytes
erzeugen würde.

Bewacht von `test_mkpfs_fassung.py`.

### `fold_inner_name_to_ascii()` in `mkpfs/pfs.py`

PFS-Verzeichniseinträge speichern Namen als ASCII. Die Vorlage gibt bei
abgeschaltetem Umbenennen (`rename_inner_image=False`) den Namen unverändert
zurück – ein Titel mit „™“ oder Gedankenstrich ergibt dann ein Abbild, das sich
gar nicht bauen lässt. Die Funktion ersetzt nur die Zeichen, die ASCII nicht
darstellen kann, und lässt den Rest stehen.

Sie stand schon in der hier eingebetteten 0.0.9 und fehlt in der Vorlage
weiterhin. Dazu gehört `import unicodedata`, das die Vorlage nicht mitbringt.

Bewacht von `test_inner_image_name.py`.

### `ExfatBuildError` und die Abweisung in `mkpfs/exfat_writer.py`

Die Vorlage laeuft in `_scan_tree()` wortlos an zwei Arten von Eintraegen
vorbei, und das Abbild hat die Datei dann einfach nicht:

* **Symlinks.** `is_dir`/`is_file` werden mit `follow_symlinks=False`
  gefragt, ein Link beantwortet also beides mit Nein und faellt durch die
  Schleife. Ein mit `rsync -a` kopierter, aus Time Machine geholter oder von
  einer SMB-Freigabe gelesener Dump kann welche tragen; auf NTFS kommen sie
  praktisch nie vor - deshalb hat es nur Mac-Anwender getroffen.
* **Namen ausserhalb von ASCII.** `_upcase_ascii` ist genau das, was der Name
  sagt, und `_name_hash` rechnet ueber dessen Ergebnis. Fuer alles andere
  weicht der Hash von der Umschalttabelle des exFAT-Treibers der Konsole ab,
  und die Datei ist dort nicht auffindbar. macOS reicht Namen zerlegt (NFD)
  weiter, ein auf Windows unauffaelliger Name kommt hier also als ASCII plus
  kombinierendem Zeichen an.

Beides wird jetzt abgewiesen statt uebergangen. `ExfatBuildError` ist von
`pfs.BuildError` getrennt, weil `pfs` dieses Modul einbindet und der
umgekehrte Weg den Kreis schliessen wuerde; wie jene erbt sie von
`RuntimeError`, breit fangende Aufrufer bleiben also heil.

Bewacht von `test_mac_befunde.py`.

### `--verify-structure` im exFAT-Zweig von `mkpfs/cli.py`

Der Zweig fragte allein `args.verify` - und `--verify-structure`, das
argparse auf True vorbelegt, wirkte dort deshalb nie. Die exFAT-Bauform ist
die uebliche, und die voreingestellte Pruefstufe der aufrufenden Oberflaeche
gibt gar keinen Schalter mit: **Jeder gewoehnliche Lauf endete, ohne ein
einziges Mal nachzusehen, was gerade geschrieben worden war.** Der
PFS-Rohzweig darueber ging immer schon ueber
`_resolve_pack_verification_mode`; dieser jetzt auch.

Bewacht von `test_mac_befunde.py`.

### `progress` für `inspect_pfs_image()` und `verify_pfs_image()` in `mkpfs/pfs.py`

`verify_file_payload_hashes()` und `validate_source_match()` können Fortschritt
melden, `inspect_pfs_image()` gab ihnen aber keinen mit – und
`verify_pfs_image()` hatte gar keinen Parameter dafür. Das Programm prüft jedes
fertige `.ffpfsc` über `verify_pfs_image()`, und diese Prüfung dekodiert jeden
Block. Bei einem 51-GB-Titel dauert das eine Viertelstunde und mehr, ohne jede
Meldung: Die Statuszeile stand still, und die Aufhänger-Erkennung schrieb am
12.09.2026 mitten in einem normalen Lauf einen Fehler ins Protokoll.

Beide Funktionen nehmen jetzt `progress` und reichen es durch. Ohne Angabe
bleibt alles wie in der Vorlage.

Bewacht von `test_mkpfs_pruefung_exfat.py`.

### Keine Kopie der Quelle für die Strukturprüfung in `mkpfs/cli.py`

`_run_stream_pack_file()` packt eine Einzeldatei direkt, ohne Zwischenkopie.
Für die Prüfung danach stellt es die Quelle aber über
`_stage_single_file_source_root()` in einem Temp-Ordner bereit: Hardlink,
sonst Symlink, sonst **vollständige Kopie**. exFAT kennt weder Hardlinks noch
Symlinks – und exFAT ist das Dateisystem, das PS5-Anwender auf ihren externen
Platten haben. Gemessen am 14.09.2026: 64 MB auf exFAT als Kopie in 2,3 s, auf
NTFS als Hardlink in 0,003 s. Bei einer 57-GB-`.ffpkg` hieß das: nach dem
Packen noch einmal 57 GB auf das Laufwerk der Quelle schreiben – für die
voreingestellte Strukturprüfung, die den Inhalt gar nicht vergleicht
(`compare_source_contents=False`). Ein am 12.09.2026 abgebrochener Lauf ließ
davon 24,8 GB neben der Quelle liegen.

`_stage_single_file_source_root()` kennt jetzt `allow_copy`. Ist es aus und
geht kein Link, liefert es `None`, und die Strukturprüfung läuft ohne den
Namens- und Größenabgleich mit der Quelle. Nur die vollständige Prüfung
(`--verify`) kopiert weiter – sie liest den Inhalt der Quelle wirklich.
`_run_post_pack_verify()` nimmt dafür `source: Path | None`;
`run_image_check()` kannte `None` schon. Der Test der Vorlage
`test_stage_single_file_source_root_falls_back_to_copyfile_when_links_unavailable`
bleibt gültig, weil ohne den neuen Schalter weiter kopiert wird.

Bewacht von `test_mkpfs_pruefung_exfat.py`.
