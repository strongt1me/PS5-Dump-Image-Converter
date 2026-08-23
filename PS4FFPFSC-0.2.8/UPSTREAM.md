# PS4 FFPFSC – eingebetteter Quellauszug

Grundlage ist **PS4 FFPFSC 0.2.8** (`PS4pkg_to_ffpfsc-0.2.8`), lizenziert unter
GPL-3.0-or-later. Der vollständige Lizenztext liegt als `LICENSE` daneben, die
Lizenzen der weiterverwendeten Fremdbestandteile in `LICENSES/` und
`THIRD_PARTY_NOTICES.md`.

## Was hier liegt

| Ordner | Inhalt |
| --- | --- |
| `ps4ffpsc/` | Der Arbeitsteil des Werkzeugs (Kommandozeile, Pipeline, PKG-Auswertung) |
| `mkpfs_1_0_0/` | MkPFS 1.0.0, die von PS4 FFPFSC geprüfte Fassung |
| `bin/` | PKG-Entpacker und DLC-Helfer, je Plattform: `*.exe` für Windows, die endungslosen Dateien für macOS auf Apple Silicon (arm64) |

## Was bewusst fehlt

- `gui.py` und `gui_model.py` – die Qt-Oberfläche der Vorlage. Der PS5 Dump &
  Image Converter bringt ein eigenes Fenster mit; dadurch entfällt PySide6
  samt Qt, also rund 115 der 119 MB der Originalfassung.
- Bauskripte, Tests und Dokumentation der Vorlage. Sie gehören zum
  Entwicklungsstand des Werkzeugs, nicht zu seiner Ausführung.

MkPFS 1.0.0 liegt bewusst **nicht** als `MkPFS-1.0.0/` im Projektstamm: Das
Programm und sein Validator suchen ihre eigene Engine über das Muster
`MkPFS-*` und würden sonst die falsche Fassung erwischen.

## Geänderte Zeilen

Die Dateien sind bis auf die folgenden Stellen unverändert übernommen.
Betroffen sind fünf: `pipeline.py`, `inventory.py`, `util.py`, `cli.py` und
`dlc_embed.py`. Alles andere ist Original 0.2.8 – nachprüfbar gegen den
Quellauszug unter `PS5 SDK usw/PS4 PKG to ffpfsc/`.

### `ps4ffpsc/pipeline.py` → `mkpfs_command()`

Die Vorlage sucht eine **installierte** MkPFS-Fassung (`import mkpfs`) und
bricht sonst mit „official MkPFS is not installed" ab; als eingefrorene
Anwendung ruft sie sich mit dem Schalter `--mkpfs` selbst auf. Beides passt
hier nicht: MkPFS liegt als Quellordner daneben, und `--mkpfs` ist im
aufnehmenden Programm nicht belegt.

Ergänzt wurde deshalb ein vorgelagerter Zweig, der

- im eingefrorenen Betrieb `--ps4-mkpfs` verwendet (den internen Schalter des
  aufnehmenden Programms) und
- im Quellbetrieb `mkpfs_1_0_0/` direkt auf den Suchpfad legt.

Die ursprüngliche Suche bleibt als letzter Ausweg stehen.

### `ps4ffpsc/pipeline.py` → Begleitdatei `*.shadowmount.txt`

Die Vorlage schreibt neben jedes fertige Abbild eine Begleitdatei und
empfahl darin `/mnt/usb0/ps4ffpsc/` als Ablageort – einen selbst angelegten
Unterordner. Am 22.08.2026 an der Konsole nachgemessen, dieselbe Datei in
derselben Sitzung:

| Ort | Ergebnis |
| --- | --- |
| `/mnt/usb0/ps4ffpsc/` | 190 s gewartet, nicht gefunden. ShadowMount+ scannte `/mnt/usb0` gezielt, ging aber nicht in den Unterordner. |
| `/mnt/usb0/` | binnen einer Sekunde eingehängt, installiert, registriert (`[REG] Installed NEW!`). |

Die Begleitdatei nennt jetzt `/mnt/usb0/` und die beiden ebenfalls
gemessenen Alternativen `/mnt/usb0/homebrew/` und `/mnt/usb0/etaHEN/games/`,
und warnt ausdrücklich vor eigenen Unterordnern sowie vor dem internen
Speicher.

### `ps4ffpsc/inventory.py` → `inspect_package()`

Der mitgelieferte Entpacker bricht beim Berechnen der Prüfsumme mit einem
Stapelüberlauf ab (`0xC00000FD`, an mehreren PKG unterschiedlicher Größe
nachgemessen). Der Rückgabewert wurde vorher nicht angesehen, deshalb galt
**jede** Datei als „unsupported_or_encrypted_pkg" – also als Fehler in der
Datei statt im Werkzeug. Jetzt wird ohne Prüfsumme wiederholt und diese in
Python nachgerechnet.

### Zu lange Zielpfade werden als solche gemeldet

`ps4_pkg_extract.exe` trägt kein `longPathAware` in seinem Manifest und endet
deshalb bei 259 Zeichen, auch wenn der Systemschalter `LongPathsEnabled`
gesetzt ist. Am 23.08.2026 an Tetris Ultimate nachgemessen: bis 183 Zeichen
Zielpfad läuft die Entpackung durch, ab 186 bricht sie ab.

Gemeldet wurde das mit Rückgabewert 3 – demselben, den der Entpacker für
„nicht unterstützt oder verschlüsselt" verwendet. `pipeline.py` unterscheidet
jetzt: eigener Status `path_too_long`, dazu eine Vorwarnung, wenn unter dem
Zielpfad weniger als 100 Zeichen frei sind. Die Erkennung steht in
`util.py` (`looks_like_path_length_failure`, `path_length_hint`) und stützt
sich auf zwei Anzeichen – den Textmarker `create_directories` und die
Pfadlänge. Die Länge ist nötig, weil der Entpacker genau an der Grenze nur
„Failed to open PKG extraction input or output" meldet.

### Abstürze werden benannt

Der Entpacker stürzt an einem bestimmten Retail-Patch mit `0xC0000005` ab und
hinterlässt dabei keine Ausgabe. Die Meldung endete deshalb hinter dem
Doppelpunkt im Nichts, davor stand nur die Dezimalzahl 3221225477.
`util.crash_description()` übersetzt den Bereich oberhalb `0xC0000000` in
Klartext; die Meldung sagt jetzt ausdrücklich, dass der Fehler im
mitgelieferten Entpacker liegt und nicht am Paket oder an der Einrichtung.

### Fehlertexte gingen ganz verloren

Vier `subprocess.run`-Aufrufe hatten kein `errors=`. Der Entpacker schreibt
seine Fehlertexte in der Windows-Codepage (`0xAE` = ®), nicht in UTF-8 – der
Lesefaden starb an einem einzigen Byte, `stdout` wurde `None`, und die
eigentliche Meldung war weg. Der `Popen`-Zweig hatte den Schalter längst.

### `ps4ffpsc/cli.py` → Meldung bei `--all`

„provide TITLE_ID or --all" erschien auch dann, wenn `--all` gerade angegeben
worden war und nur kein brauchbares Spiel im Inventar stand. Jetzt getrennte
Meldungen für ein leeres Inventar und für abgelehnte Pakete.

### Plattformauswahl der nativen Helfer

`inventory.find_extractor()` hatte die Namen fest als
`("ps4_pkg_extract.exe", "ps4_pkg_extract")` – die Windows-Datei zuerst, auf
**jeder** Plattform. Da beide Fassungen im selben `bin/` liegen, griff macOS
zur `.exe` und meldete `[Errno 13] Permission denied`.
`dlc_embed.find_dlc_helper()` machte es von jeher richtig; hier fehlte es.

Dazu kommt: Der Bauplan legt den Ordner unter `datas` ab, wobei das
Ausführungsrecht verlorengeht – obwohl Git `ps4_pkg_extract` als `100755`
führt. `util.ensure_executable()` zieht es nach. Ohne das galt der
DLC-Helfer auf macOS als „nicht vorhanden", ein stiller Ausfall ohne Meldung.

### `ps4ffpsc/pipeline.py` → `load_or_scan()` prüft die Herkunft

Der zwischengespeicherte `package_inventory.json` wurde ungeprüft
zurückgegeben, sobald er existierte. `list` ist der einzige Befehl, der ihn
ohne `refresh=True` anfordert – und genau ihn ruft die Oberfläche beim
Einlesen auf.

Im reinen Kommandozeilenbetrieb fällt das kaum auf, weil dort jede Quelle
üblicherweise ihren eigenen Arbeitsordner bekommt. Die Oberfläche benutzt für
**jede** Quelle denselben (`<Ziel>/ps4ffpsc_arbeit`). Damit ergab sich der am
23.08.2026 aus der Praxis gemeldete Ablauf:

1. Erstes PKG-Backup einlesen – alles korrekt angezeigt.
2. Zweites Backup einlesen – es kam der Bestand des **ersten** zurück, mit
   Verweisen auf Dateien, die zur neuen Quelle nicht passen: Fehler.
3. Danach scheiterte auch das erste Backup, das eben noch funktioniert hatte.

Der Bestand hält seine Herkunft von jeher fest – `selected_pkg_files`,
`selected_dump_dirs` und `pkg_dir`. Verglichen wurde sie nur nie. `load_or_scan`
tut das jetzt und scannt bei Abweichung neu; Groß-/Kleinschreibung und
Trennzeichen bleiben dabei egal, sonst würde jedes Einlesen neu scannen.

Bewusst **nicht** `list` auf `refresh=True` umgestellt: Das würde auch das
wiederholte Einlesen derselben Quelle jedes Mal neu scannen, was bei großen
Backups Minuten kostet. Die Prüfung gehört an die Stelle, die den Bestand
ausgibt.

## Plattformen

Der Hersteller liefert fertige Programmdateien nur für **Windows x64** und
**macOS ARM64**. Beide Sätze liegen hier nebeneinander in `bin/`. Dass die Suche je nach
System den passenden Namen findet, war bis v1.8.86 nur die Absicht und
nicht der Zustand - siehe: Plattformauswahl der nativen Helfer (oben).

Für **Linux** und für **Intel-Macs** gibt es keine – dort meldet das Fenster
das offen, statt mitten im Lauf stehen zu bleiben. Selbst übersetzen ließe
sich der Entpacker aus den Quellen der Vorlage (`tools/ps4_pkg_extract`,
CMake + C++), das ist hier bewusst nicht eingebaut.
