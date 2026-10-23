# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.2** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (MIT) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Seit 21.10.2026 steht die Versionskonstante auf **2.2.10**. ps5-ultrapack 2.2.8 bis 2.2.10 aendern am C#-Teil
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
