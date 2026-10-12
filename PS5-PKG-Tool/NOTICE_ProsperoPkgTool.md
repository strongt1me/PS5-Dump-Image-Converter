# NOTICE – ProsperoPkgTool (der zweite Paketersteller)

Grundlage ist **ProsperoPkgTool 0.3.0** von pearlxcore
(<https://github.com/pearlxcore/ProsperoPkgTool>), Commit
`f2c91cd7a5d8440b7b9ae5e0b1154334093bf613` (11.10.2026), lizenziert unter der
**MIT-Lizenz** (Text in `LICENSE-ProsperoPkgTool`). Laut eigenem README eine
"clean-room reimplementation" – kein gemeinsamer Code mit LibProsperoPkg (Sven­GDK,
GPL-3.0-or-later), das `ffpfsc-pkg-tool` seit v1.9.71 nutzt. Credits im eigenen
README: SvenGDK.

**Wunsch des Nutzers (12.10.2026):** Im Fenster „PS5 PKG Dump & Image Converter“ zwei
Paketersteller zur Wahl stellen, wie es die eigene Vorlagen-App des Nutzers schon tut
(„Standard-Builder“: LibProsperoPkg 1.2.0 / ProsperoPkgTool). Eingebaut ist das nur für
**Aufgabe „Paket bauen“** (`convert`-Befehl) – Lesen, Prüfen und Entpacken bleiben beim
bestehenden `ffpfsc-pkg-tool` (eigenes `--json`, CNT-Metadaten-Zusammenführung,
Passcode-Durchreichung, Fortschritt); ProsperoPkgTool kennt keine JSON-Ausgabe, nur
Klartext-Zeilen.

## Was hier liegt

| Datei | Inhalt |
|---|---|
| `<Plattform>/ProsperoPkgTool(.exe)` | die gebaute, eigenstaendige Befehlszeile, framework-abhaengig (net10.0, dieselbe Laufzeit wie `ffpfsc-pkg-tool`) |
| `<Plattform>/ProsperoPkgTool.dll`/`.deps.json`/`.runtimeconfig.json` | dazugehoerige .NET-Dateien |
| `LICENSE-ProsperoPkgTool` | MIT-Lizenz von pearlxcore |

**Keine eigenen NuGet-Abhaengigkeiten** (`ProsperoPkgTool.csproj` listet keine
`PackageReference`) – nur eingebettete Ressourcen (Schluessel-Rohlinge, ein
`right.sprx`). Vier Plattformen wie `ffpfsc-pkg-tool`: win-x64, linux-x64, osx-arm64,
osx-x64; nur win-x64 lokal geprueft (siehe unten).

## So wurde gebaut

Quelle: `git clone --depth 1 https://github.com/pearlxcore/ProsperoPkgTool.git`
(Commit `f2c91cd7`), ohne Aenderung, mit dem .NET-SDK 10.0.401:

```
dotnet publish ProsperoPkgTool/ProsperoPkgTool.csproj -c Release -r <rid> --self-contained false -o <Ziel>
```

SHA-256 der win-x64-Dateien (Bau vom 12.10.2026):

```
513562835a1412d01b9d4efa3a9a4cb2e3b7d0a30b28e299bf6bc916e314072a  ProsperoPkgTool.exe
e67b8e90f5c88e6c6442f06584aa84452445bceb5c1002c6bf800a5ef376017e  ProsperoPkgTool.dll
```

## Gemessen am 12.10.2026 (nur Windows, nur `convert`/`img_*`, keine echte Konsole)

* `img_info`/`img_file_list`/`img_verify`/`img_extract` an einem echten Debug-Paket
  (528 MB, "PS5 Arcade Game Zone"): Titel, Content-ID und Fassung stimmen mit
  `ffpfsc-pkg-tool inspect`; `img_extract` liefert 178 Dateien, **byteweise gleich**
  mit `extract-inner` fuer alle Dateien **ausser** `sce_sys/*` – `img_extract` holt die
  nicht aus der aeusseren CNT-Huelle (das macht nur `ffpfsc-pkg-tool`, deshalb bleibt
  das Lesen bei ihm). `img_verify`: 9 pass, 3 "unsupported" (RSA-Signatur,
  Block-Digests, PlayGo-CRC – laut eigenem README nicht implementiert), 0 fail.
* `convert` aus dem mit `ffpfsc-pkg-tool` entpackten Spielordner gebaut (ohne Passcode):
  lief durch (11 s), erkennt bereits fake-signierte Module und laesst sie stehen.
  Mit `ffpfsc-pkg-tool validate --json` am Ergebnis geprueft: dieselben drei Befunde
  wie am **unveraenderten Originalpaket** (fehlendes `license.dat`/`.info` bei
  `applicationDrmType: upgradable`, PS4-SELF-Magie in `eboot.bin` – beides Eigenschaften
  dieses Testpakets, keine durch den Bau eingefuehrten Fehler) **plus ein neuer Befund**:
  `cnt.playgo-layout` (PlayGo-Tabellengroesse 32 statt 64) – eine echte Abweichung beim
  Neubau der PlayGo-Daten, passend zum README-Hinweis, dass PlayGo noch nicht vollstaendig
  ist. **An einer echten PS5 ungeprueft.**
* Kein Kreuzvergleich mit `img_create`/Ordner-Quelle (nur GP5-Projekte oder
  Rueckbackup-Ordner) und keine Pruefung unter Linux/macOS.

## Aktualisieren

1. Neuen Commit klonen, SHA-256 der Binaerdateien notieren.
2. Mit den Parametern oben fuer alle vier Plattformen bauen.
3. Diese Datei (Commit, Pruefsummen, Datum der Messung) nachfuehren.
4. Die Testreihe (`test_prospero_pkg_tool.py`, `test_ps5_pkg_optionen.py`) laufen lassen.
