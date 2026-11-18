# PS5-PKG-Tool

`ffpfsc-pkg-tool` fuer das Fenster „PS5 PKG Dump & Image Converter“ - gebaut aus dem Quelltext von
**ps5-fpkg-converter 0.0.3** (GPL-3.0-or-later, `src/`); darin die Engine von ps5-ultrapack (Quelltext aus der MIT-Zeit bis 2.4.1) und die
Bibliothek **LibProsperoPkg 1.2.0** (GPL-3.0-or-later; als fertige Datei `src/ffpfsc-pkg-tool/lib/`, die Quelle
dazu liegt nicht bei - siehe `src/ffpfsc-pkg-tool/lib/README.md`).

Geprueft am 18.11.2026: **ps5-ultrapack 2.6.0** (18.11.2026) ist **nicht** uebernommen, die Versionskonstante bleibt auf **2.5.1**. Anders als
2.4.2 bis 2.5.1 aendert 2.6.0 den C#-Teil in der Sache: Der Vergleich 2.5.1 bis 2.6.0 nennt unter `backend/native/src/ffpfsc-pkg-tool/` die neuen
Dateien `InnerInPackage.cs` (schreibt das innere Abbild gleich an seinen Platz im Paket) und `SourceImage.cs` (liest eine `.ffpfs`/`.ffpfsc` als
Bauquelle an Ort und Stelle), Aenderungen an `Program.cs` (`build` mit Abbild als Quelle), `AmprIndex.cs` und `PkgTool.csproj` und eine andere
gepatchte `LibProsperoPkg.dll` (Bau a3ee4c1a aus fpkg-gui 0.6.12 statt d7090eb6; Einzelheiten in `lib/README.md` und `patches/` dort). Alles
betrifft nur den **Paketbau** (`build`); dieses Programm ruft ihn seit 17.11.2026 nicht mehr auf (Pakete baut allein Dump Forge) und nutzt von
dem Werkzeug nur `validate`, `list-inner` und `extract-inner`. Die Konstante auf 2.6.0 zu heben waere unwahr (der Quelltext waere nicht der
von 2.6.0), und die Neufassung zu uebernehmen hiesse, GPL-3.0-or-later-Quelltext mit Zusatzbedingungen nach Abschnitt 7 samt einer anderen
gepatchten Bibliothek einzubauen - ohne Nutzen fuer die drei Befehle, die hier laufen, und gegen die Entscheidung vom 16.11.2026 (kein
Quelltext der Fassungen ab 2.4.2). Die Neuerungen der Upstream-App (Option "In place", Formatfilter, Platzberechnung, Packen mit Faeden)
betreffen die Oberflaeche und die Python-Seite. Sollte der Paketbau dieses Werkzeugs wieder gebraucht werden, ist 2.6.0 der Stand, der
zusammengefuehrt werden muss (Dreiwege-Zusammenfuehrung mit unserem Befehl `stream-inner`, vier Plattformen neu bauen).

Seit 31.10.2026 steht die Fassung auf **0.0.3** (30.10.2026). Der Vergleich 0.0.2 bis 0.0.3 nennt keine Datei unter `src/`
(nur `app/engine.py`, `app/ui.py`, die Hilfetexte und `pyproject.toml` der Python-Oberflaeche des Autors) - das C#-Werkzeug hier
ist also unveraendert. Uebernommen ist die eine Verhaltensaenderung, die auch fuer unser Fenster zaehlt: Mit einem Temp-Ordner
setzt der Aufruf auch `TMP`, `TEMP` und `TMPDIR` des Werkzeugs (`ps5_pkg_werkzeug._umgebung`) und legt den Ordner an, damit keine
Zwischendatei auf dem Systemlaufwerk landet. An keinem echten Paket gemessen.

Seit 16.11.2026 steht die Versionskonstante auf **2.5.1**. ps5-ultrapack 2.4.2 bis 2.5.1 aendern am C#-Teil nur den Kopf jeder Datei (drei Zeilen mit Lizenz- und Urheberhinweis) und die Konstante: Der Vergleich 2.4.1 bis 2.5.1 nennt unter `backend/native/src/ffpfsc-pkg-tool/` die zehn C#-Dateien, und nach Abzug des neuen Kopfes und der Konstante sind sie Zeichen fuer Zeichen gleich 2.4.1; `lib/` und `patches/` sind unveraendert, die gepatchte `LibProsperoPkg.dll` bleibt dieselbe Datei. **Lizenz:** Seit 2.4.2 steht ps5-ultrapack unter GPL-3.0-or-later mit Zusatzbedingungen nach Abschnitt 7 (Datei `NOTICE` dort: Urheberhinweise und Nennung bleiben, geaenderte Fassungen werden als solche gekennzeichnet); bis einschliesslich 2.4.1 ist es MIT. Der C#-Quelltext hier stammt aus der Zeit davor (ps5-fpkg-converter 0.0.3) - uebernommen wird nur die Versionsnummer, kein Quelltext der neueren Fassung. `ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut (nur diese Datei je Ordner; `dotnet publish -r <rid> --self-contained false`, wie bei 2.4.1); `dotnet ... version` zeigt 2.5.1 und LibProsperoPkg 1.2.0. Nicht uebernommen: die Neuerungen der Upstream-App (zstd-Packs fuer jedes Spiel, Intel-Mac-Fassung, Info-Seite mit der Lizenz) - sie betreffen die Oberflaeche und die Python-Seite der Upstream-App, nicht den C#-Teil hier. An keinem echten Paket gemessen.

Seit 12.11.2026 steht die Versionskonstante auf **2.4.1**. ps5-ultrapack 2.4.1 aendert am C#-Teil nur die Konstante: Der Vergleich 2.4.0 bis 2.4.1 nennt unter `backend/native/src/ffpfsc-pkg-tool/` nur `Program.cs` (eine Zeile, die Konstante); `lib/` und `patches/` sind unveraendert, die gepatchte `LibProsperoPkg.dll` bleibt dieselbe Datei. `ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut (nur diese Datei je Ordner; `dotnet publish -r <rid> --self-contained false`, wie bei 2.4.0); `dotnet ... version` zeigt 2.4.1 und LibProsperoPkg 1.2.0. Nicht uebernommen: die Korrekturen der Upstream-App (nicht verbundenes Ausgabelaufwerk, PS4-Archive mit verschluesselten Dateinamen, mehrteilige RAR) - sie betreffen die Oberflaeche und die Auftragsliste der Upstream-App, nicht den C#-Teil hier. An keinem echten Paket gemessen.

Seit 09.11.2026 steht die Versionskonstante auf **2.4.0**. ps5-ultrapack 2.4.0 (Windows, macOS und Linux aus einer Freigabe) aendert am C#-Teil nur die Konstante: Der Vergleich 2.3.4 bis 2.4.0 nennt unter `backend/native/src/ffpfsc-pkg-tool/` nur `Program.cs` (zwei Zeilen, die Konstante); `lib/` und `patches/` sind unveraendert, die gepatchte `LibProsperoPkg.dll` bleibt dieselbe Datei. `ffpfsc-pkg-tool.dll` ist in allen vier Ordnern neu gebaut (nur diese Datei je Ordner; `dotnet publish -r <rid> --self-contained false`, wie bei 2.3.4); `dotnet ... version` zeigt 2.4.0 und LibProsperoPkg 1.2.0. Nicht uebernommen: die Neuerungen der Upstream-App (Linux-Fassung, Arbeitsspeicher als Zwischenspeicher) und die Korrektur zum verschluesselten `about`-Modul beim Backport - sie betreffen die Oberflaeche und den Backport der Upstream-App, nicht den C#-Teil hier. An keinem echten Paket gemessen.

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
