# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.2** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (MIT) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Seit 27.10.2026 steht die Versionskonstante auf **2.3.2**. ps5-ultrapack 2.3.2 aendert am C#-Teil nur Kommentare und
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
