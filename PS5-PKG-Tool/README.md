# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.3** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (MIT) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Seit 31.10.2026 steht die Fassung auf **0.0.3** (30.10.2026). Der Vergleich 0.0.2 bis 0.0.3 nennt keine Datei unter `src/`
(nur `app/engine.py`, `app/ui.py`, die Hilfetexte und `pyproject.toml` der Python-Oberflaeche des Autors) - das C#-Werkzeug hier
ist also unveraendert. Uebernommen ist die eine Verhaltensaenderung, die auch fuer unser Fenster zaehlt: Mit einem Temp-Ordner
setzt der Aufruf auch `TMP`, `TEMP` und `TMPDIR` des Werkzeugs (`ps5_pkg_werkzeug._umgebung`) und legt den Ordner an, damit keine
Zwischendatei auf dem Systemlaufwerk landet. An keinem echten Paket gemessen.

Seit 08.11.2026 steht die Versionskonstante auf **2.3.4**. ps5-ultrapack 2.3.4 aendert am C#-Teil nur die Konstante und die Bibliothek: Die gepatchte `LibProsperoPkg.dll` (SHA-256 `cd43389f...`, gegen `lib/SHA256SUMS` des Autors geprueft) bekommt einen fuenften IL-Patch, der lokalisierte `icon0_NN.dds` und `pic1_NN.dds` im Paket behaelt (vorher fiel jede `.dds` ausser icon0, pic0, pic1 und pic2 heraus, und der Bau scheiterte an seiner eigenen Pruefung, wenn ein Spiel sie mitbringt). `lib/README.md`, `lib/SHA256SUMS`, `patches/README.md` und `patches/CecilPatch/Program.cs` sind die Dateien des Autors von 2.3.4; `LibProsperoPkg.dll.orig` ist unveraendert. `ffpfsc-pkg-tool.dll` und `LibProsperoPkg.dll` sind in allen vier Ordnern neu (`dotnet publish`, nur diese zwei Dateien je Ordner uebernommen); `dotnet ... version` zeigt 2.3.4 und LibProsperoPkg 1.2.0. An keinem echten Paket mit lokalisierten Bildern gemessen.

Seit 29.10.2026 steht die Versionskonstante auf **2.3.3**. ps5-ultrapack 2.3.3 aendert nur die Oberflaeche der Upstream-App
(`PS5_UltraPack.py`: mehrere Auftraege fuer dieselbe Quelle, Zusatzinhalte, die schon als gleiche Datei da sind, zaehlen als
abgelegt) und ihre Tests - der Vergleich 2.3.2 bis 2.3.3 nennt keine C#-Datei; `lib/` und `patches/` sind unveraendert. Unsere
Konstante ist auf 2.3.3 gehoben, `ffpfsc-pkg-tool.dll` in allen vier Ordnern neu gebaut; `dotnet ... version` zeigt 2.3.3 und
LibProsperoPkg 1.2.0. An keinem echten Paket gemessen.

Davor (27.10.2026): **2.3.2**. ps5-ultrapack 2.3.2 aendert am C#-Teil nur Kommentare und
Leerraum (Vergleich der Dateien ohne Kommentare und Leerzeichen: Program.cs und Ps4Keystone.cs je nur Zeilenende-Leerraum, alle
anderen gleich; `lib/` und `patches/` unveraendert); Upstream selbst haelt die Konstante noch auf 2.3.1. Unsere Konstante ist
auf 2.3.2 gehoben, `ffpfsc-pkg-tool.dll` in allen vier Ordnern neu gebaut (nur diese Datei je Ordner); `dotnet ... version`
zeigt 2.3.2 und LibProsperoPkg 1.2.0.

Davor (24.10.2026): **2.3.1**. ps5-ultrapack 2.3.0 und 2.3.1 bringen im C#-Teil neue Dateien
`Ps4Keystone.cs` (`ps4-keystone`), `Ps4Rebind.cs` (`ps4-rebind`), `Ps4Sfo.cs` (`ps4-sfo`) und `SafeConsole.cs` und aendern
`Program.cs` (`build --keystone`, Zielpfade) und `Ps4.cs`; `lib/` und `patches/` sind gleich geblieben. `Program.cs` und die README
des Werkzeugs sind per Dreiwege-Zusammenfuehrung uebernommen (Basis Upstream 2.2.10, unsere Fassung mit dem Befehl
`stream-inner`, Ziel Upstream 2.3.1), ohne Konflikte; `Ps4.cs` und die vier neuen Dateien sind die Upstream-Fassung.
`ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut (nur diese Datei je Ordner); `dotnet ... version` zeigt 2.3.1 und
LibProsperoPkg 1.2.0. Das Fenster im Programm nutzt die neuen Befehle nicht - sie sind nur im Werkzeug. An keinem echten
Paket gemessen.

Davor (21.10.2026): **2.2.10**. ps5-ultrapack 2.2.8 bis 2.2.10 aendern am C#-Teil
`Program.cs` (u. a. festes Zahlenformat fuer das geparste Baulog, Dateien werden per Umbenennen ersetzt statt durchschrieben,
ein unvollstaendiges Entpacken schlaegt jetzt fehl) und `Ps4.cs`; `lib/` und `patches/` sind gleich geblieben. Beide Dateien
sind per Dreiwege-Zusammenfuehrung uebernommen (Basis Upstream 2.2.7, unsere Fassung mit dem Befehl `stream-inner`, Ziel
Upstream 2.2.10), ohne Konflikte; `ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut. Ersetzt wurde nur diese eine
Datei je Ordner; der Neubau liefert auch eine andere `LibOrbisPkg.dll` und `ffpfsc-pkg-tool.exe` (Quelle unveraendert), die
bleiben, wie sie waren.

Davor (18.10.2026): Versionskonstante 2.2.7 (ps5-ultrapack 2.2.5 bis 2.2.7 aenderten am C#-Teil nur die Konstante).

Gebaut am 21.10.2026 mit .NET SDK 10.0.401, **framework-abhaengig** (net10.0; das Programm braucht die .NET-
Laufzeit 10 ohnehin), je Plattform ein Ordner:

```
dotnet publish src/ffpfsc-pkg-tool/PkgTool.csproj -c Release -r <rid> --self-contained false -o <rid>
```

Die Datei `PkgTool.csproj` ist gegenueber dem Original auf `net10.0`, `SelfContained=false` und
`PublishSingleFile=false` umgestellt; sonst unveraendert. `win-x64` ist an einem echten Paket gemessen;
`linux-x64`, `osx-arm64` und `osx-x64` sind gebaut, aber nicht gestartet.
