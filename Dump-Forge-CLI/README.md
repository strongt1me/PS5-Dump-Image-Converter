# Dump-Forge-CLI

Die Befehlszeile **`ps5-dump-forge`** von **Dump Forge** ([quer3q/ps5-dump-forge](https://github.com/quer3q/ps5-dump-forge),
GPL-3.0-or-later). Das Programm ruft sie im Bereich „PKG / FPKG“ auf, um aus Spielordnern und Abbildern (`.ffpkg`,
`.ffpfsc`, `.ffpfs`, `.exFAT`) ein Debug-Paket (FPKG, die Datei endet auf `.pkg`) zu bauen - so, wie es die aktuelle
Fassung von Dump Forge selbst tut: Forge liest die Quelle ohne Zwischenordner (auch das Abbild in einer `.ffpfsc`),
baut das Paket, liest es zurück und prüft es. Das Programm baut Forges Weg nicht nach, es führt Forge selbst aus
(`ps5_validator/utils/forge_cli.py`).

```
ps5-dump-forge inspect <Quelle> --json
ps5-dump-forge convert <Quelle> --to pkg -o <Datei.pkg> [--kraken fast|balanced|smallest|stored]
                       [--threads N] [--full-verify] [--remove-backport]
```

Der Fortschritt kommt als eine JSON-Zeile je Ereignis auf stdout (`stages`, `progress`, `log`, `done`).

## Fassung und Herkunft

**Dump Forge v0.6.0**, Freigabe vom 26.11.2026 (Quelltext: <https://github.com/quer3q/ps5-dump-forge/tree/v0.6.0>).
Seit 0.6.0 liefert der Autor keine Archive mehr, sondern je Betriebssystem und Architektur eine blanke Datei
(`ps5-dump-forge-cli-<Fassung>-…`). Die Dateien hier sind diese Anhänge, unverändert und nur umbenannt. Bei allen sechs stimmt
die SHA-256 mit `SHA256SUMS` der Freigabe und mit dem Digest überein, den GitHub für den Anhang meldet (26.11.2026).

| Ordner | Datei | SHA-256 der Datei | Anhang der Freigabe |
|---|---|---|---|
| `win-x64/` | `ps5-dump-forge.exe` | `1b637a921d2a356e542681611f52ea38c44877381a6d5c0291b71d47071c6686` | `ps5-dump-forge-cli-0.6.0-windows-x86-64.exe` |
| `macos-arm64/` | `ps5-dump-forge` (Apple Silicon) | `336f3f9385b9682841b054dc58d767bf5a9a79f55281bf82c37fe67d7e9c463e` | `ps5-dump-forge-cli-0.6.0-macos-arm64` |
| `macos-x64/` | `ps5-dump-forge` (Intel) | `f2275e1ffa5fb2f79c643fdba6c4f13660993861ec9f04f5b65c2d3ead75b86c` | `ps5-dump-forge-cli-0.6.0-macos-x86-64` |
| `linux-x64/` | `ps5-dump-forge` (statisch) | `6b950e280a57ac7bf4ffdc2e6d9ab9fbc6e037ba4ccebd2aacf441bd5e361fd6` | `ps5-dump-forge-cli-0.6.0-linux-x86-64` |
| `win-arm64/` | `ps5-dump-forge.exe` (nativ arm64) | `96159000036cd70b0d1e87533359e0c54aef0031b6701e6bf876fd5e1e4301c8` | `ps5-dump-forge-cli-0.6.0-windows-arm64.exe` |
| `linux-arm64/` | `ps5-dump-forge` (statisch) | `2f2080fcd8472aa16961765cbbf337e3ada7da48a1b640018b8fba396f540f94` | `ps5-dump-forge-cli-0.6.0-linux-arm64` |

`LICENSE` (GPL-3.0) und `THIRD-PARTY-NOTICES.md` (die Hinweise zu den in Forge enthaltenen Fremdteilen: ps5upload-Engine,
ampr-emu-ng, LZ4 und andere) liegen der Freigabe nicht mehr als Anhang bei; sie stammen aus dem Quelltext der Marke `v0.6.0`.
Gegenüber 0.5.7 ist `LICENSE` byte-gleich; die Hinweise nennen jetzt ps5upload v12.6.30 und nur noch ampr-emu-ng v0.5.1
(das früher beiliegende ampr_emu 0.4.2.1 ist entfallen).

**macOS** (26.11.2026): Bis 0.5.7 gab es eine gemeinsame Datei für beide Macs (`macos-universal/`). Seit 0.6.0 gibt es je
Architektur eine; das Programm wählt nach `platform.machine()` (`forge_cli.unterordner()`), und ins Bündel kommt nur die
Datei seiner Architektur. Beide wurden hier **nicht ausgeführt** (kein Mac zur Hand): geprüft sind Herkunft, Prüfsumme,
Dateikopf (64-Bit-Mach-O, cputype arm64 bzw. x86_64) und die Fassung in der Datei; ausgeführt werden sie im Mac-Lauf der CI
(Schritt „Dump-Forge-Befehlszeile im fertigen Buendel“).

**arm64** (17.11.2026, berichtigt 27.11.2026): `win-arm64/` ist die native Befehlszeile. Auf einem ARM-Rechner meldet auch ein
x64-Python bzw. die x64-EXE `ARM64` (Python 3.14 liest die Architektur über WMI); gebündelt ist in der Windows-EXE nur `win-x64/`,
und jede Suche fällt darauf zurück (`forge_cli.unterordner_reihe`). `linux-arm64/` ist seit 0.6.0 wie `linux-x64/` statisch
gebunden und lief am 26.11.2026 unter arm64-Emulation (Docker: `inspect` und Paketbau mit Rückgabe 0). `win-arm64/` wurde
**nicht ausgeführt** (kein arm64-Rechner zur Hand): geprüft sind Herkunft, Prüfsumme, Dateikopf (PE Machine `0xAA64`) und die
Fassung `0.6.0` in der Datei (`tests/test_forge_cli.py`, `MitgelieferteBefehlszeilenTests`).

**Was 0.6.0 am Paketbau ändert** (gemessen 26.11.2026 an einem Spiel mit AMPR EMU): Ein `.pkg` trägt keine AMPR-Laufzeit
mehr; Forge lässt `fakelib/libSceAmpr.sprx` weg („a .pkg carries no AMPR runtime, the console's loader provides it“). Bis
0.5.7 setzte es dort ampr_emu 0.4.2.1 ein. Bei jeder anderen Umwandlung setzt 0.6.0 das mitgelieferte ampr-emu-ng 0.5.1 ein.
`inspect --json` nennt den Paketbau eigens (`lz4.pkg_runtime_action`); das Programm richtet seine Rückfrage danach.

Auf einer Plattform ohne Ordner (zum Beispiel Linux auf RISC-V) fehlt die Befehlszeile; das Fenster baut dann kein Paket und sagt
es. Gebaut wird seit 17.11.2026 nur noch mit Dump Forge.

## Neue Fassung einspielen

1. Die Anhänge `ps5-dump-forge-cli-<Fassung>-…` der Freigabe laden und gegen `SHA256SUMS` und den GitHub-Digest prüfen.
2. Je Plattform als `ps5-dump-forge[.exe]` in den Ordner legen, `LICENSE` und `THIRD-PARTY-NOTICES.md` aus dem Quelltext der Marke ersetzen; die Dateien
   für Linux und macOS brauchen das Ausführungsrecht (`git update-index --chmod=+x`; das gilt auch für `linux-arm64/`).
3. Diese Tabelle, die Zeile in `THIRD_PARTY_LICENSES.md` und `werkzeug_updates.py` (`dump-forge-cli`) nachziehen;
   `tests/test_forge_cli.py` baut mit der mitgelieferten Befehlszeile ein echtes Paket.
