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
