# UFS2Tool 4.1 — ps5conv-Patch: Dateien > 2 GB entpacken

**Datum:** 2026-09-13
**Grundlage:** UFS2Tool 4.1.0 (SvenGDK, https://github.com/SvenGDK/UFS2Tool), BSD-2-Clause.

## Problem
Das unveränderte UFS2Tool 4.1 kann aus einer `.ffpkg` (UFS2) **keine Datei > 2 GB
entpacken**. `Ufs2Image.ReadFile()` liest die ganze Datei in ein `byte[inode.Size]`
und wirft bei `inode.Size > int.MaxValue` (2 147 483 647):

    File too large to read into memory (… exceeds 2,147,483,647 byte limit).

Betroffen sind beide Wege, weil beide über `ReadFile()` laufen:
* der `extract`-Unterbefehl (`ExtractFile` → `ReadFile` → `File.WriteAllBytes`),
* der Dokan-Mount (`Ufs2DokanOperations.ReadFile` → `_image.ReadFile`),
  der bei > 2 GB schon beim ersten Read `ERROR_INVALID_FUNCTION` / `[Errno 22]` wirft.

Gemessen am 13.09.2026 an *Double Dragon Revive* (`projectdd-ps5.pak`, 6,8 GB).

## Änderung (nur `Ufs2Image.cs`)
* Neu: `ReadFileToStream(uint inodeNumber, Stream output)` sowie
  `StreamIndirectBlock` / `StreamDoubleIndirectBlock` / `StreamTripleIndirectBlock`
  und `CatchUpZeros`. Spiegeln die vorhandene Blocklogik, schreiben aber jeden
  Datenblock direkt in einen `Stream` statt in ein Gesamt-`byte[]`; Sparse-Löcher
  werden als Nullen aufgefüllt. Kein 2-GB-Limit mehr.
* `ExtractFile()` streamt jetzt über `ReadFileToStream` direkt in die Zieldatei
  (kein `ReadFile()`+`WriteAllBytes` mehr).
* `ReadFile()` (byte[]-API, für Symlinks u.a. < 2 GB) und der Dokan-Read-Pfad
  bleiben unverändert — das Projekt nutzt für > 2 GB ausschließlich
  `UFS2Tool extract` (mount-frei).

## Nachweis
`extract` der 6,8-GB-`.ffpkg` liefert die Datei byte-genau
(SHA-256 `9162559fc4337cfe0810198e6c5d0d5398c9ae825cde3be7b1494e4e5811fac1`,
51 Dateien, 10 639 294 098 Bytes — identisch zum Original-Dump). Ebenso end-to-end
über Aufgabe 4 (`.ffpkg` → Dump-Ordner) im Programm.

## Neu bauen (alle vier gebündelten Plattformen)
Quelle: die unveränderte UFS2Tool-4.1-Quelle (Herkunft oben) mit diesem
`Ufs2Image.cs` ersetzt, dann je Ziel:

    dotnet publish UFS2Tool.csproj -c Release -r <win-x64|linux-x64|osx-x64|osx-arm64> \
      --self-contained true -p:PublishTrimmed=true -p:PublishSingleFile=true \
      -p:InvariantGlobalization=true -p:DebugType=none

Ergebnis-Binärdatei nach `UFS2Tool-4.1/<ziel>/` kopieren und die SHA-256/bytes in
`UFS2Tool-4.1/pruefsummen.json` nachtragen (die Laufzeit prüft sie).

## Neubau am 17.09.2026: .NET 8 → .NET 10

Grund ist kein Fehler, sondern ein Ablaufdatum: **.NET 8 endet am 10.11.2026**,
danach gibt es für die mitgelieferte Laufzeit keine Sicherheitskorrekturen mehr.
.NET 10 ist LTS (bis 14.11.2028) und wird vom mitgelieferten ProsperoPkg
ohnehin verlangt.

Geändert wurde **nur** `<TargetFramework>net8.0</TargetFramework>` →
`net10.0` in `UFS2Tool.csproj`; der Patch oben blieb unverändert. Gebaut mit
SDK 10.0.303, eingebettete Laufzeit **10.0.11**, dieselben vier Ziele und
dieselben Schalter wie oben. Vor dem Einsetzen geprüft: Das Original
`Ufs2Image.cs` aus 4.1 enthält `ReadFileToStream` nicht (sonst wäre der Patch
auf einem fremden Stand gelandet), und jede gebaute Datei hat das erwartete
Format (Windows PE, ELF x86_64, Mach-O x86_64, Mach-O arm64).

| Ziel | .NET 8 | .NET 10 |
| --- | --- | --- |
| `win-x64` | 12.460.254 B | 13.312.989 B |
| `linux-x64` | 13.570.309 B | 15.015.507 B |
| `osx-x64` | 13.545.753 B | 14.459.465 B |
| `osx-arm64` | 12.823.561 B | 13.671.289 B |

**Noch offen:** Der Windows-Bau verlangt per Manifest Administratorrechte, ein
Probelauf war hier deshalb nicht möglich. Der Beweis über eine echte `.ffpkg`
steht damit aus – `RUN_FFPKG_INTEGRATION=1` im erhöhten Terminal.
