# ProsperoPkg 2.5 — Herkunft und Neubau

## Was hier liegt

`win-x64/prosperopkg.exe` ist eine schmale Kommandozeilen-Hülle um
**LibProsperoPkg 2.5**, eine Bibliothek, die PS5-Pakete baut und liest.

Das Programm ruft sie als **eigenen Prozess** auf — genauso wie `mkpfs`
und `UFS2Tool`. Das ist keine Bequemlichkeit, sondern Absicht:
LibProsperoPkg steht unter **GPL-3**, dieses Programm nicht. Fest
dazugelinkt würde die GPL auf das ganze Projekt durchschlagen. Über die
Prozessgrenze bleibt die Trennung sauber.

## Herkunft

| | |
|---|---|
| Bibliothek | LibProsperoPkg 2.5 |
| Lizenz | GNU GPL, Version 3 (siehe `LICENSE`, `NOTICE`) |
| Quelle | `LibProsperoPKG-2.5/` im SDK-Ordner des Anwenders |
| Zielplattform | `net10.0` — dieselbe, die das Programm für WPF lädt |
| Umfang | 137 C#-Dateien, rund 32.000 Zeilen |
| Übernommen am | 29.08.2026 |

Die Hülle selbst (`src/ProsperoPkgCli/`) gehört zu diesem Projekt und ist
bewusst dünn: Argumente einlesen, Werte aus `sce_sys/param.json`
ergänzen, die Bibliothek rufen, Zeilen ausgeben. Alles Fachliche bleibt
in der Bibliothek.

**GPL-Pflicht:** Wer die gebaute `LibProsperoPkg.dll` weitergibt, muss
ihren Quellcode mitgeben oder anbieten. Für den Eigengebrauch entsteht
diese Pflicht nicht; sie beginnt mit der Weitergabe.

## Neu bauen

Gebraucht wird das **.NET-10-SDK** (`dotnet --list-sdks` muss eine
10er-Fassung zeigen).

```
dotnet build ProsperoPkg-2.5/src/ProsperoPkgCli/ProsperoPkgCli.csproj ^
  -c Release -o ProsperoPkg-2.5/win-x64 -p:DebugType=none
```

**Warum `-p:DebugType=none`.** Ohne diesen Schalter legt der Bau neben
jede Bibliothek eine `.pdb` mit Fehlersuchangaben. Die werden hier nie
gebraucht: Der Ordner steht nicht in `PS5ImageConverter_Pro.spec`, kommt
also gar nicht in die EXE, und die Huelle gibt bei einem Fehler nur
`ex.GetType().Name` und `ex.Message` aus - nie eine Stapelspur.

Dafuer tragen sie zweierlei nach draussen: den **absoluten Baupfad** des
Rechners, auf dem gebaut wurde, und eine **SourceLink-Karte** auf das
Repository, aus dem gebaut wurde. Am 01.09.2026 zeigte
`prosperopkg.pdb` damit auf ein geloeschtes Repository und
`LibProsperoPkg.pdb` (571 KB) auf ein zweites. Beide wurden entfernt.

Liegen die Bibliotheksquellen anderswo, wird der Pfad mitgegeben:

```
dotnet build ProsperoPkg-2.5/src/ProsperoPkgCli/ProsperoPkgCli.csproj ^
  -c Release -o ProsperoPkg-2.5/win-x64 ^
  -p:LibProsperoPkgProject="<Pfad>\src\LibProsperoPkg\LibProsperoPkg.csproj"
```

Die Vorgabe steht in `ProsperoPkgCli.csproj`.

## Aufruf

```
prosperopkg inspect --source <Backup-Ordner>
prosperopkg build   --source <Backup-Ordner> --out <Zielordner> [Optionen]
```

`inspect` liest nur und sagt, ob ein Backup als Debug-Paket starten
würde. Die letzte Zeile lautet `RESULT: READY` oder `RESULT: NOT_READY`;
blockierende Module stehen als `BLOCKER:`-Zeilen davor.

`build` erzeugt ein finalisiertes Debug-Abbild (`\x7FFIH`). Die letzte
Zeile lautet `RESULT: <Pfad zur .pkg>`. Fehlende Angaben (Content-ID,
Title-ID, Titel, Version) werden aus `sce_sys/param.json` des
Quellordners ergänzt.

## Was es kann — und was nicht

Erzeugbar sind zwei Ausgabeformate:

* `DebugImage` (`\x7FFIH`) — **das vollständige, installierbare Paket**
* `MetadataContainer` (`\x7FCNT`) — nur Metadaten, nicht installierbar

und vier Paketarten: `Application`, `Homebrew`, `AdditionalContentData`
und `AdditionalContentNoData` (also auch DLC).

Ausdrücklich **nicht** möglich:

* **Retail-Finalisierung** (signed byte `0x80`). Sie braucht Material,
  das nur die Konsole selbst hat.
* Ein echter `rif`-Lizenzschlüssel. Der ist mit konsolenspezifischem
  Material verschlüsselt und lässt sich nicht am Rechner erzeugen.

Die Bibliothek sagt über ihre eigenen Ergebnisse: *„On-console
installation acceptance is not guaranteed."* Sie prüft Struktur und
Rundlauf; ob die Konsole ein Paket annimmt, hängt an deren Betriebsart
und Firmware.

## `--schnell`: der Kraken-Encoder ohne Optimal-Parse

Kraken ist Closed Source. Sony hat es fuer die PS5 lizenziert und einen
*Hardware-Decoder* verbaut; der **Encoder** bleibt proprietaer (RAD Game
Tools / Epic). Was in LibProsperoPkg rechnet, ist deshalb eine
vollstaendige Nachbildung in verwaltetem C# — sie kann keine echte
Oodle-Bibliothek einbinden (kein `DllImport`, kein `oo2core`).

Die Kommentare im Encoder sagen, die Produktionsvorgabe sei der schnelle
Greedy-Parse, und `UseOptimalParse` steht auch auf `false`. Zwei andere
Schalter stehen aber auf `true`:

```
ProductionOptimalSingleChunk      = true
ProductionWindowedOptimal         = true
ProductionOptimalWindowedMaxBlock = 0x40000   // 256 KB
```

Und der Kommentar zum Fenstergrenzwert sagt selbst, 0x40000 *"covers a
full PFSC block, so every single-chunk block above
ProductionOptimalMaxBlock"* gehe ueber den gefensterten Optimal3-DP.
Praktisch laeuft also fast jeder Block durch den teuren Parse — nur eben
nicht ueber den Schalter, der so heisst.

**Gemessen am 29.08.2026**, gleiche Quelle (Arkanoid Eternal Battle,
1,05 GB Dump), gleiche Maschine:

| Weg | Laufzeit | Ergebnis |
|---|---|---|
| Vorgabe | **134 min abgebrochen** | keines |
| `--schnell` | **319 s** | 393,6 MB `.pkg` |

Mindestens 25-mal schneller. Das Ergebnis ist ein vollwertiges
finalisiertes Debug-Abbild: `\x7fFIH`, `full_debug`, `format_version=3`,
19 Entries, `param.json` im Paket lesbar.

Die Felder sind `internal static`, und die Bibliothek bringt kein
`InternalsVisibleTo` mit. Die Option setzt sie deshalb ueber
**Reflexion** — bewusst so: Die Bibliothek bleibt unveraendert, und der
Eingriff steht an einer Stelle in `Program.cs`, statt sich im Fremdcode
zu verstecken. Findet sich ein Feld nicht, sagt das Werkzeug es und baut
trotzdem weiter; eine andere Fassung darf die Namen aendern.

Zwei Vorbehalte: Der schnellere Parse erzeugt **groessere** Pakete (wie
viel genau, ist offen — der Vergleichslauf wurde nie fertig), und ob die
Konsole ein so gebautes Paket genauso annimmt, muss der Versuch zeigen.

## Was ein Backup mitbringen muss

`inspect` prüft die Bedingungen, die eine Konsole im Debug-Betrieb
stellt:

* `eboot.bin` ist vorhanden,
* die Metadaten liegen als `param.json` vor, nicht als PS4-`param.sfo`,
* **jedes** ausführbare Modul ist entweder ein rohes ELF oder ein SELF
  mit Fake-Autorität (`authority_id` beginnt mit `0x31`).

Ein signiertes **und verschlüsseltes** Modul blockiert. Am 29.08.2026 an
drei echten Backups gemessen: Arkanoid Eternal Battle und Asterix &
Obelix Heroes waren startbereit, Crazy Chicken Shooter nicht — dort
lagen fünf verschlüsselte Systembibliotheken in `fakelib/`, die der
Backport dort eingesetzt hatte.

## Linux-Bau (03.09.2026)

Neben `win-x64/` liegt jetzt `linux-x64/`. Erzeugt mit demselben
SDK, nur mit Zielangabe:

```
dotnet publish ProsperoPkg-2.5/src/ProsperoPkgCli/ProsperoPkgCli.csproj \
  -c Release -r linux-x64 --self-contained false \
  -o ProsperoPkg-2.5/linux-x64 -p:DebugType=none
```

**Framework-abhängig, wie der Windows-Bau.** 1,3 MB gegen 81 MB für einen
eigenständigen Bau; dafür muss auf dem Linux-Rechner .NET 10 liegen. Fehlt
es, sagt das Programm es deutlich ("You must install .NET to run this
application") — kein stiller Fehlschlag. Am 03.09.2026 in WSL Ubuntu
nachgemessen: ohne Laufzeit diese Meldung, der eigenständige Bau lief dort
auch ohne .NET durch.

**Das Ausführungsrecht setzt `prosperopkg.werkzeug_finden()` selbst.** Weder
NTFS noch eine ZIP-Datei trägt es weiter; ohne das `chmod` startet der
Linux-Bau nicht. Dieselbe Vorkehrung wie bei UFS2Tool in
`werkzeuge_bereitstellen.ufs2tool_bereitstellen`.

## macOS-Bau (03.09.2026)

`osx-x64/` entstand auf demselben Weg, nur mit `-r osx-x64`. Der zunächst
vermutete Hinderungsgrund – im SDK-Ordner liege nur ein `osx-arm64`-Bau der
Bibliothek – trifft nicht zu: Gebaut wird aus dem **Quelltext**, und
LibProsperoPkg ist verwalteter Code ohne Plattformbindung. Ein
vorkompiliertes Abbild wird gar nicht gebraucht.

Nachgemessen wurde das Dateiformat, weil genau hier schon einmal ein
unbrauchbarer Helfer entstand (siehe `PS4FFPFSC-0.2.8/UPSTREAM.md`):

| Ordner | Größe | Format |
| --- | --- | --- |
| `win-x64` | 162 KB | PE (Windows) |
| `linux-x64` | 78 KB | ELF x86-64 |
| `osx-x64` | 89 KB | Mach-O 64, `cpu 0x01000007` = x86_64 |

**Apple Silicon ist mit abgedeckt.** `plattformordner()` unterscheidet
seit dem 03.09.2026 nicht nur das Betriebssystem, sondern auch den
Prozessor – dieselbe Unterscheidung wie
`werkzeuge_bereitstellen.ufs2tool_kennung`. Ohne den zweiten Teil bekäme
ein Mac mit M-Prozessor den Intel-Bau untergeschoben; der liefe dort nur
über Rosetta 2, und ohne Rosetta fände macOS gar keine passende
Architektur.

| Ordner | Größe | Format |
| --- | --- | --- |
| `win-x64` | 162 KB | PE |
| `linux-x64` | 78 KB | ELF x86-64 |
| `osx-x64` | 89 KB | Mach-O 64, `cpu 0x01000007` = x86_64 |
| `osx-arm64` | 125 KB | Mach-O 64, `cpu 0x0100000c` = arm64 |

Alle vier Wege sind durchgespielt: Betriebssystem und Prozessor
vorgegeben, den gewählten Ordner geprüft und die Kopfbytes der Datei
gelesen. Das Dateiformat wird gemessen, nicht am Namen abgelesen – genau
hier entstand beim PS4-Helfer schon einmal ein unbrauchbarer Bau.
