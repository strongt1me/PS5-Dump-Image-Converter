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

**Dump Forge v0.5.7**, Freigabe vom 22.11.2026 (Quelltext: <https://github.com/quer3q/ps5-dump-forge/tree/v0.5.7>).
Die Dateien stammen unverändert aus den Archiven der Freigabe. Bei allen fünf Archiven stimmt deren
SHA-256 mit `SHA256SUMS` der Freigabe und mit dem Digest überein, den GitHub für den Anhang meldet (Dreierprobe, 22.11.2026).

| Ordner | Datei | SHA-256 der Datei | aus dem Archiv der Freigabe (SHA-256 des Archivs) |
|---|---|---|---|
| `win-x64/` | `ps5-dump-forge.exe` | `a847df998d952bf7ebb75d64a53ce9cd820d4c2682052de34bd5fe7c53a0081f` | `ps5-dump-forge-0.5.7-windows-x86-64.zip` (`c569c39d692fbf1fad71035be6dc75937a33e8591ee84666a0d9c616ad918134`) |
| `macos-universal/` | `ps5-dump-forge` | `48f5bd723359a2275abf3ee03a92b0782a62c5df1a07a058ff208e2c763fb0d8` | `ps5-dump-forge-0.5.7-macos-universal.zip` (`de47e5a4954b945fd0fd854b31173966bbc7543e73ddf9f570283cc400048d39`) |
| `linux-x64/` | `ps5-dump-forge` (statisch, musl) | `b62b60cfbf9c71a5b41fd68de5545b8aa3ec88828f02bdedc93f1f838fcb8cf6` | `ps5-dump-forge-0.5.7-linux-x86-64-musl.tar.gz` (`f0c6b2201731c630a77215c4326c75d3c832841ea7eccdd74ba75178e1f7d364`) |
| `win-arm64/` | `ps5-dump-forge.exe` (nativ arm64) | `20c1aec0e0e082e049c158b5fc721e89adf25fd244b3a8a9706d8cf85b4070c5` | `ps5-dump-forge-0.5.7-windows-arm64.zip` (`80373c7d7d61f28a914796df2d3e1945ecf42c064578d3a8dec89e3b2cc4f582`) |
| `linux-arm64/` | `ps5-dump-forge` (dynamisch, glibc ab 2.34) | `79ad4e9c76170ee21f1d6a28c79a86c896d73c572dd5d04ac09b8b5d11473240` | `ps5-dump-forge-0.5.7-linux-arm64.tar.gz` (`830ca7414d7853c7872e8eb418877f19ef52d4c4afd3c7391e7aaff93c084e53`) |

`LICENSE` (GPL-3.0) und `THIRD-PARTY-NOTICES.md` (die Hinweise zu den in Forge enthaltenen Fremdteilen: ps5upload-Engine,
ampr_emu, ampr-emu-ng, LZ4 und andere) sind die Dateien der Freigabe (in 0.5.7 byte-gleich denen von 0.5.6).

**arm64** (17.11.2026): `win-arm64/` ist die native Befehlszeile; sie gilt, wenn das Programm mit einem arm64-Python läuft (ein
x64-Python meldet auf einem ARM-Rechner `AMD64` und nimmt `win-x64`; fehlt `win-arm64/`, fällt die Suche auf `win-x64/` zurück).
`linux-arm64/` ist anders als `linux-x64/` nicht statisch, sondern gegen glibc gebunden (Marke `GLIBC_2.34`): Forge liefert für
arm64 nur das große Archiv mit der Oberfläche, die Befehlszeile daraus ist die Datei hier (seit 0.5.7 gibt es zusätzlich ein statisches Archiv `linux-arm64-musl`, das hier nicht verwendet wird). Beide wurden **nicht ausgeführt** (kein
arm64-Rechner zur Hand): geprüft sind Herkunft, Prüfsumme, Dateikopf (PE Machine `0xAA64`, ELF `e_machine` `0xB7`) und die
Fassung `0.5.7` in der Datei (`tests/test_forge_cli.py`, `MitgelieferteBefehlszeilenTests`).

Auf einer Plattform ohne Ordner (zum Beispiel Linux auf RISC-V) fehlt die Befehlszeile; das Fenster baut dann kein Paket und sagt
es. Gebaut wird seit 17.11.2026 nur noch mit Dump Forge.

## Neue Fassung einspielen

1. Archiv der Freigabe laden und gegen `SHA256SUMS` und den GitHub-Digest prüfen.
2. `ps5-dump-forge[.exe]` je Plattform in den Ordner legen, `LICENSE` und `THIRD-PARTY-NOTICES.md` ersetzen; die Dateien
   für Linux und macOS brauchen das Ausführungsrecht (`git update-index --chmod=+x`; das gilt auch für `linux-arm64/`).
3. Diese Tabelle, die Zeile in `THIRD_PARTY_LICENSES.md` und `werkzeug_updates.py` (`dump-forge-cli`) nachziehen;
   `tests/test_forge_cli.py` baut mit der mitgelieferten Befehlszeile ein echtes Paket.
