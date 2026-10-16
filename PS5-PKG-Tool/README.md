# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.2** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (MIT) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Seit 16.10.2026 steht die Versionskonstante auf **2.2.5** (ps5-ultrapack 2.2.3 bis 2.2.5 aendern am C#-Teil nur diese Zeile und
stellen die Konsolenausgabe auf UTF-8 um - `Console.OutputEncoding` am Anfang von `Main`; `lib/` und `patches/` sind gleich
geblieben) und `ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut. Ersetzt wurde nur diese eine Datei je Ordner; der
Neubau liefert auch eine andere `LibOrbisPkg.dll` und `ffpfsc-pkg-tool.exe` (Quelle unveraendert), die bleiben, wie sie waren.

Gebaut am 08.10.2026 mit .NET SDK 10.0.401, **framework-abhaengig** (net10.0; das Programm braucht die .NET-
Laufzeit 10 ohnehin), je Plattform ein Ordner:

```
dotnet publish src/ffpfsc-pkg-tool/PkgTool.csproj -c Release -r <rid> --self-contained false -o <rid>
```

Die Datei `PkgTool.csproj` ist gegenueber dem Original auf `net10.0`, `SelfContained=false` und
`PublishSingleFile=false` umgestellt; sonst unveraendert. `win-x64` ist an einem echten Paket gemessen;
`linux-x64`, `osx-arm64` und `osx-x64` sind gebaut, aber nicht gestartet.
