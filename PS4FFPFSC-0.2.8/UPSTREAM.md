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

Die Dateien sind unverändert übernommen – mit einer Ausnahme:

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

## Plattformen

Der Hersteller liefert fertige Programmdateien nur für **Windows x64** und
**macOS ARM64**. Beide Sätze liegen hier nebeneinander in `bin/`; die Suche des
Werkzeugs findet je nach System den passenden Namen (`ps4_pkg_extract.exe`
bzw. `ps4_pkg_extract`).

Für **Linux** und für **Intel-Macs** gibt es keine – dort meldet das Fenster
das offen, statt mitten im Lauf stehen zu bleiben. Selbst übersetzen ließe
sich der Entpacker aus den Quellen der Vorlage (`tools/ps4_pkg_extract`,
CMake + C++), das ist hier bewusst nicht eingebaut.
