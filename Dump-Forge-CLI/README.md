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
Die Dateien stammen unverändert aus den Archiven der Freigabe. Bei den ersten drei (Windows x64, macOS, Linux x64) stimmt deren
SHA-256 mit `SHA256SUMS` der Freigabe und mit dem Digest überein, den GitHub für den Anhang meldet (Dreierprobe); bei den zwei
arm64-Archiven (17.11.2026) nur mit dem Digest von GitHub - `SHA256SUMS` wurde dafür nicht eigens geladen.

| Ordner | Datei | SHA-256 der Datei | aus dem Archiv der Freigabe (SHA-256 des Archivs) |
|---|---|---|---|
| `win-x64/` | `ps5-dump-forge.exe` | `c883d2e22b941f4a5a870bce230968756ad23b2c17ef7443e427418487200077` | `ps5-dump-forge-0.5.6-windows-x86-64.zip` (`9944ef56709c668925e4134c8827cd47ab4247a9a61e09c6e3a3c071d952cf11`) |
| `macos-universal/` | `ps5-dump-forge` | `cadf210f5e13a408afea7e4530b25effd1e668dc042d4b9802e6826fb37e77c2` | `ps5-dump-forge-0.5.6-macos-universal.zip` (`601d7a6f75ac92f7bf6b71b0c4b45ce62d855f7812441834757ce4eb70bc3276`) |
| `linux-x64/` | `ps5-dump-forge` (statisch, musl) | `742f702f8fb2b4752da5df6c5dbb27b4e2b8fa6d9113ce2a1cf892d14feaa495` | `ps5-dump-forge-0.5.6-linux-x86-64-musl.tar.gz` (`0a13a4a61b3bbeb7ba73eb4ef543a35ba3717e739e0f986e136d6856cfbc735c`) |
| `win-arm64/` | `ps5-dump-forge.exe` (nativ arm64) | `93d93cbf7e788ff8cecf29c0db7f24645aad0c51841717b6c89106408fb58496` | `ps5-dump-forge-0.5.6-windows-arm64.zip` (`ca0bc140245c08a8189c1e6069665d7bccbc76807d324fc93e6b9e0df7744187`) |
| `linux-arm64/` | `ps5-dump-forge` (dynamisch, glibc ab 2.34) | `edd4df446c78f4c5bfd2a1dbd85f6d04e6b4fc119ae520db23dfd7b2892810df` | `ps5-dump-forge-0.5.6-linux-arm64.tar.gz` (`c7ddfe308d23051ec15de465a34ce6c8f7def152d801b0f310ec6e68454f8d6d`) |

`LICENSE` (GPL-3.0) und `THIRD-PARTY-NOTICES.md` (die Hinweise zu den in Forge enthaltenen Fremdteilen: ps5upload-Engine,
ampr_emu, ampr-emu-ng, LZ4 und andere) sind die Dateien der Freigabe (gleich dem Stand v0.5.6 im Quelltext).

**arm64** (17.11.2026): `win-arm64/` ist die native Befehlszeile; sie gilt, wenn das Programm mit einem arm64-Python läuft (ein
x64-Python meldet auf einem ARM-Rechner `AMD64` und nimmt `win-x64`; fehlt `win-arm64/`, fällt die Suche auf `win-x64/` zurück).
`linux-arm64/` ist anders als `linux-x64/` nicht statisch, sondern gegen glibc gebunden (Marke `GLIBC_2.34`): Forge liefert für
arm64 nur das große Archiv mit der Oberfläche, die Befehlszeile daraus ist die Datei hier. Beide wurden **nicht ausgeführt** (kein
arm64-Rechner zur Hand): geprüft sind Herkunft, Prüfsumme, Dateikopf (PE Machine `0xAA64`, ELF `e_machine` `0xB7`) und die
Fassung `0.5.6` in der Datei (`tests/test_forge_cli.py`, `MitgelieferteBefehlszeilenTests`).

Auf einer Plattform ohne Ordner (zum Beispiel Linux auf RISC-V) fehlt die Befehlszeile; das Fenster baut dann kein Paket und sagt
es. Gebaut wird seit 17.11.2026 nur noch mit Dump Forge.

## Neue Fassung einspielen

1. Archiv der Freigabe laden und gegen `SHA256SUMS` und den GitHub-Digest prüfen.
2. `ps5-dump-forge[.exe]` je Plattform in den Ordner legen, `LICENSE` und `THIRD-PARTY-NOTICES.md` ersetzen; die Dateien
   für Linux und macOS brauchen das Ausführungsrecht (`git update-index --chmod=+x`; das gilt auch für `linux-arm64/`).
3. Diese Tabelle, die Zeile in `THIRD_PARTY_LICENSES.md` und `werkzeug_updates.py` (`dump-forge-cli`) nachziehen;
   `tests/test_forge_cli.py` baut mit der mitgelieferten Befehlszeile ein echtes Paket.
