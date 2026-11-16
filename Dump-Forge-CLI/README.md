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

**Dump Forge v0.5.6**, Freigabe vom 16.11.2026 (Quelltext: <https://github.com/quer3q/ps5-dump-forge/tree/v0.5.6>).
Die drei Dateien stammen unverändert aus den Archiven der Freigabe; deren SHA-256 stimmt mit `SHA256SUMS` der Freigabe
und mit dem Digest überein, den GitHub für den Anhang meldet (Dreierprobe).

| Ordner | Datei | SHA-256 der Datei | aus dem Archiv der Freigabe (SHA-256 des Archivs) |
|---|---|---|---|
| `win-x64/` | `ps5-dump-forge.exe` | `c883d2e22b941f4a5a870bce230968756ad23b2c17ef7443e427418487200077` | `ps5-dump-forge-0.5.6-windows-x86-64.zip` (`9944ef56709c668925e4134c8827cd47ab4247a9a61e09c6e3a3c071d952cf11`) |
| `macos-universal/` | `ps5-dump-forge` | `cadf210f5e13a408afea7e4530b25effd1e668dc042d4b9802e6826fb37e77c2` | `ps5-dump-forge-0.5.6-macos-universal.zip` (`601d7a6f75ac92f7bf6b71b0c4b45ce62d855f7812441834757ce4eb70bc3276`) |
| `linux-x64/` | `ps5-dump-forge` (statisch, musl) | `742f702f8fb2b4752da5df6c5dbb27b4e2b8fa6d9113ce2a1cf892d14feaa495` | `ps5-dump-forge-0.5.6-linux-x86-64-musl.tar.gz` (`0a13a4a61b3bbeb7ba73eb4ef543a35ba3717e739e0f986e136d6856cfbc735c`) |

`LICENSE` (GPL-3.0) und `THIRD-PARTY-NOTICES.md` (die Hinweise zu den in Forge enthaltenen Fremdteilen: ps5upload-Engine,
ampr_emu, ampr-emu-ng, LZ4 und andere) sind die Dateien der Freigabe (gleich dem Stand v0.5.6 im Quelltext).

Nicht mitgeliefert: Windows arm64 (läuft dort als x64) und Linux arm64 (Forge liefert dafür nur das große Archiv mit der
Oberfläche, keine statische Befehlszeile). Auf diesen Plattformen fehlt der Ordner; das Fenster baut Spielordner dann über
LibProsperoPkg weiter, ein Abbild nimmt es dort nicht an und sagt es.

## Neue Fassung einspielen

1. Archiv der Freigabe laden und gegen `SHA256SUMS` und den GitHub-Digest prüfen.
2. `ps5-dump-forge[.exe]` je Plattform in den Ordner legen, `LICENSE` und `THIRD-PARTY-NOTICES.md` ersetzen; die Dateien
   für Linux und macOS brauchen das Ausführungsrecht (`git update-index --chmod=+x`).
3. Diese Tabelle, die Zeile in `THIRD_PARTY_LICENSES.md` und `werkzeug_updates.py` (`dump-forge-cli`) nachziehen;
   `tests/test_forge_cli.py` baut mit der mitgelieferten Befehlszeile ein echtes Paket.
