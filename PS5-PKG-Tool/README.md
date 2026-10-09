# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.2** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (MIT) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Gebaut am 08.10.2026 mit .NET SDK 10.0.401, **framework-abhaengig** (net10.0; das Programm braucht die .NET-
Laufzeit 10 ohnehin), je Plattform ein Ordner:

```
dotnet publish src/ffpfsc-pkg-tool/PkgTool.csproj -c Release -r <rid> --self-contained false -o <rid>
```

Die Datei `PkgTool.csproj` ist gegenueber dem Original auf `net10.0`, `SelfContained=false` und
`PublishSingleFile=false` umgestellt; sonst unveraendert. `win-x64` ist an einem echten Paket gemessen;
`linux-x64`, `osx-arm64` und `osx-x64` sind gebaut, aber nicht gestartet.
