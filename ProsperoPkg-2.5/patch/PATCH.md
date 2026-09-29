# LibProsperoPkg 2.6.0 — ps5conv-Patch: NAPS-u2c-Überlauf bei vielen kleinen Dateien

**Datum:** 2026-09-29
**Grundlage:** LibProsperoPkg 2.6.0 (SvenGDK/LibProsperoPKG, `main` Commit
`748eabf1b7d17819528cabf367d8e27109d8fce3`), GPL-3.0-or-later.

## Problem

„PKG bauen“ scheiterte seit v1.9.21 (Umstieg von 2.5 auf 2.6.0) bei echten
Dumps mit vielen kleinen Dateien:

    System.NotSupportedException: NAPS u2c delta value 752 exceeds the
    single-byte field; this layout size is not supported.

Gemessen an *Arkanoid Eternal Battle* (kleinster verfügbarer Test-Dump,
~1,2 GB, 1166 Dateien) — deterministisch reproduzierbar.

## Ursache (am Quelltext gemessen, nicht geraten)

Die `naps_pkg_layout.dat`-Tabelle „u2c“ hält je Gruppe von 8 logischen
256-KiB-Blöcken (`ublock`) ein Byte-Delta zum Index des zugehörigen
`CblockInfo`-Eintrags (`ProsperoNapsLayoutBuilder.BuildU2c`). Die
Tabellengröße (`NumU2cEntries = (NumUBlocks + 8) >> 3`) hängt **nur** an der
Titelgröße, nicht an der Dateizahl — das Format erwartet also ungefähr
**einen Eintrag je 256-KiB-Bereich**.

Zwei Stellen verletzten diese Annahme:

1. **`ProsperoNwonlyNapsGenerator.Generate`** öffnete bei **jeder** Datei
   eine eigene „RUN“ (Cursor-Neuanker), unabhängig davon, ob überhaupt eine
   Lücke im On-Disk-Bytestrom entstand. Das verdoppelte die
   `CblockInfo`-Eintragszahl unnötig (gemessen: 2356 → 1201 Einträge allein
   durch diese Korrektur).
2. **`ProsperoPs5InnerImageAssembler`/`DeriveDataRegionBlocks`** vergab **je
   komprimierter Datei genau einen `CblockInfo`-Eintrag**, unabhängig von
   ihrer Größe. Bei hunderten winziger Dateien im selben logischen Bereich
   (z. B. Level-Daten, jede wenige KB) entstanden dadurch weit mehr
   Einträge in einem 2,3-MiB-Fenster, als ein Byte darstellen kann
   (gemessen: bis **1538** statt erlaubten 255).

Ob 2.5.0 dasselbe Problem hätte: **ja** — derselbe Algorithmus steht dort
unverändert, nur mit einem ungeprüften `(byte)`-Cast statt der 2.6.0
hinzugefügten Prüfung. 2.5.0 hätte also **still ein beschädigtes u2c-Verzeichnis**
gebaut (Wertüberlauf ohne Fehlermeldung) statt korrekt abzubrechen — ein
Rückbau auf 2.5.0 wäre keine Lösung, sondern eine stillere, schlechtere
Variante desselben Fehlers.

## Änderung (zwei Dateien)

* **`ProsperoNwonlyNapsGenerator.cs`** — eine RUN wird nur noch geöffnet,
  wenn der On-Disk-Bytestrom wirklich eine Lücke hat (Blockausrichtung)
  oder zwischen roh und komprimiert wechselt; der komprimierte Cursor hält
  sonst von selbst Schritt (`WalkBlocks` addiert je Block exakt
  `StreamLength`, die für aneinandergereihte Dateien gleich ihrer echten
  Byteanzahl — `OnDiskSize` — ist). Dieselbe „RUN nur am Blockanfang, nicht
  je Element“-Regel verwendet der Metadatenblock in derselben Datei bereits
  (`StartRun = i == 0`); hier wird sie konsequent auch auf die Datenregion
  angewendet.
* **`ProsperoPs5InnerImageAssembler.cs`** — aufeinanderfolgende kleine
  komprimierte Dateien (nicht `sce_sys`, nicht der Keystone) werden vor dem
  Bauen zu Bündeln von bis zu 256 KiB unkomprimierter Gesamtgröße
  zusammengefasst und **gemeinsam als ein einziger Kraken-Strom** neu
  komprimiert. Sie teilen sich dadurch **einen** `CblockInfo`-Eintrag — genau
  dieselbe „ein Eintrag, beliebige Größe“-Mechanik, die eine einzelne große
  komprimierte Datei im selben Format ohnehin schon benutzt (im selben
  Test-Dump enthalten: eine 341-MiB-Datei mit nur einem Eintrag). Logische
  Adressen (fidx/afid) bleiben unverändert — nur wie die Bytes **auf der
  Platte** komprimiert werden, ändert sich. Neues Feld `FileNode.Grouped`
  markiert eine in ein Bündel aufgegangene Datei; sie bekommt keinen
  eigenen Platzierungseintrag mehr (`Placements`-Projektion gefiltert).

## Nachweis

* **Arkanoid Eternal Battle** baut mit dem Patch ohne den u2c-Abbruch
  (vorher: 100 % reproduzierbarer Absturz).
* **Kompressions-Rundlauf byte-genau geprüft**, unabhängig vom bekannten,
  separaten Indirektblock-Fehler beim Entpacken großer äußerer Container:
  `ProsperoCompressedPfsImage.Pack`/`Unpack` auf **25 echten Bündeln aus dem
  Dump (377 Dateien** aus den Ordnern, die den Überlauf ausgelöst hatten:
  `Levels/Battle/Phase 1/{Easy,Hard,Medium}`, `Levels/LocalVersus/Levels`,
  `Levels/Solo`, `shaders/2D`) — alle 25 Bündel byte-für-byte identisch nach
  Kompression/Dekompression.
* Diagnose-Instrumentierung (klemmt statt zu werfen, protokolliert Gruppe/
  Fenster/Index) bestätigte vor der Korrektur exakt die oben genannten
  Werte; nach beiden Änderungen: 0 Überlauf-Zeilen im gesamten Build.

## Tiefere Grenze, die dieser Patch NICHT löst (29.09.2026, zweiter Testtitel)

Ein zweiter, andersartiger Dump (*Instant Sports Plus*, 2,5 GB, 323 Dateien)
zeigt: Der Patch hilft, löst das Problem aber **nicht allgemein**.

Das Feld `next-base` in `BuildU2c` ist kein lokaler, sondern ein
**globaler** Index in die gesamte `CblockInfo`-Liste des Titels
(`entry[4] = first[8*g+8]`, roh, ohne Bezug zu einer Gruppenbasis). Damit
darf die **Gesamtzahl** aller Einträge im ganzen Titel nie 255
übersteigen — unabhängig davon, wie gut kleine Dateien lokal gebündelt
sind. Gemessen:

| Titel | Dateien | `numCblockInfo` nach Bündelung | Baut? |
| --- | --- | --- | --- |
| Arkanoid Eternal Battle | 1166 | **106** | ja, 0 Überlauf |
| Instant Sports Plus | 323 | **492** | nein, Überlauf bleibt |

Instant Sports Plus hat einen einzelnen zusammenhängenden Lauf von 250
Dateien (2,28 GiB roh) — viele davon einzeln bereits größer als der
2-MiB-Bündeldeckel, sodass sie gar nicht erst gebündelt werden und je
einen eigenen Eintrag behalten. Ein größerer oder fehlender Deckel hilft
nicht grundsätzlich: Ganz ohne Deckel bricht der Bau an einer **zweiten,
unabhängigen** Grenze ab — dem bereits dokumentierten
Indirektblock-Limit des äußeren Containers (`project_pkg_indirektblock_verdacht`):
eine einzelne Inner-Image-Datei darf höchstens rund 569 MiB belegen
(9112 Blöcke `ib[0]`); bei 2,5 GB Quelldaten wird diese Grenze so oder so
erreicht, egal wie das u2c-Layout aussieht.

**Fazit:** Dieser Patch macht „PKG bauen“ für **kleine/einfache** Titel
zuverlässig (gemessen: Arkanoid), löst aber **nicht** das allgemeine
Problem für größere, komplexere Titel. Dafür bräuchte es entweder echte
Sony-Formatdokumentation oder ein echtes, dicht gepacktes Referenzpaket
von Sony selbst, um die *wahre* Kodierung von `next-base` zu bestimmen —
vermutlich relativ zu etwas, das nicht der rohe Gesamtindex ist. Genau
das ist wahrscheinlich der Grund, warum PS5PKGTool für „real titles“ auf
die nicht-öffentliche LibProsperoPkg 1.2.0 ausweicht, statt 2.5/2.6.0 zu
patchen: Die vollständige Lösung braucht Wissen, das aus der öffentlichen
Quelle allein nicht herzuleiten ist.

## Was NICHT geprüft ist

**Kein Konsolentest.** Das gebaute `.pkg` ist PC-seitig wohlgeformt
(Magic, FIH-Struktur, Größenangaben) und der Kompressionsschritt ist
byte-genau bewiesen — ob die PS5 das veränderte u2c-Layout beim
tatsächlichen Spielstart korrekt liest, zeigt erst ein echter Start auf
der Konsole. Das Vollentpacken über `ProsperoPackageExtractor` ist an
diesem Build **nicht** prüfbar, weil ein unabhängiger, bereits vor diesem
Patch bekannter Fehler (Indirektblock `ib[1]`, siehe
`project_pkg_indirektblock_verdacht`) bei ausreichend großen äußeren
Containern zuschlägt — dieser Patch ändert daran nichts.

## Neu bauen (alle vier gebündelten Plattformen)

Wie in `UPSTREAM.md` beschrieben, nur mit den beiden Dateien aus diesem
Ordner über die entsprechenden Pfade der 748eabf-Quelle kopiert, dann:

```
dotnet build ProsperoPkg-2.5/src/ProsperoPkgCli/ProsperoPkgCli.csproj ^
  -c Release -o ProsperoPkg-2.5/win-x64 -p:DebugType=none ^
  -p:LibProsperoPkgProject="<Pfad>\src\LibProsperoPkg\LibProsperoPkg.csproj"

dotnet publish ProsperoPkg-2.5/src/ProsperoPkgCli/ProsperoPkgCli.csproj \
  -c Release -r <linux-x64|osx-x64|osx-arm64> --self-contained false \
  -o ProsperoPkg-2.5/<ziel> -p:DebugType=none \
  -p:LibProsperoPkgProject=<Pfad>/src/LibProsperoPkg/LibProsperoPkg.csproj
```

`LibProsperoPkg.dll` ist verwalteter Code ohne Plattformbindung und bei
allen vier Bauten byte-gleich (wie schon vor diesem Patch); nur die
native `prosperopkg`/`prosperopkg.exe`-Hülle unterscheidet sich je Ziel.
