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
beiden unten genannten Stellen. Das Programm legt beim Start das
**übergeordnete** Verzeichnis auf `sys.path`; `import mkpfs` findet die Engine
dann von selbst.

Dazu `LICENSE` – der GPL-3.0-Text der Vorlage, unverändert. Er bleibt beim
Quellcode, den er deckt; die Nennung in `THIRD_PARTY_LICENSES.md` sagt, wozu
die Engine im Programm dient, ersetzt den Lizenztext aber nicht. Bis zum
03.09.2026 fehlte er hier als einziger unter allen eingebetteten
Fremdkomponenten.

## Was bewusst fehlt

- `mkpfs/gui/` – die mitgelieferte Oberfläche (16 Dateien). Sie verlangt
  `customtkinter` und `Pillow`; der PS5 Dump & Image Converter bringt sein
  eigenes Fenster mit. Dieselbe Entscheidung wie bei PS4 FFPFSC, siehe
  `PS4FFPFSC-0.2.8/UPSTREAM.md`.
- `tests/`, `.github/`, `assets/`, `scripts/` und die Baudateien der Vorlage.
  Sie gehören zum Entwicklungsstand des Werkzeugs, nicht zu seiner Ausführung.

## Nicht zu verwechseln mit `PS4FFPFSC-0.2.8/mkpfs_1_0_0/`

Daneben liegt eine **zweite** 1.0.0 – die, welche PS4 FFPFSC 0.2.8 mitliefert,
samt dessen Patch. Die beiden sind nicht dasselbe:

| | `MkPFS-1.0.0/` (hier) | `PS4FFPFSC-0.2.8/mkpfs_1_0_0/` |
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

Zwei Stellen, beide in eigenen Abschnitten unten. Beide sind Zutaten dieses
Projekts und **müssen bei jedem Fassungswechsel erneut nachgetragen
werden** – am 03.09.2026 haben sie den Austausch überstanden, weil vorher
nachgesehen wurde, nicht von selbst.

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
