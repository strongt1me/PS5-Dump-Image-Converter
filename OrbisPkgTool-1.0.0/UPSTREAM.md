# OrbisPkgTool – mitgelieferte Befehlszeile

Grundlage ist **OrbisPkgTool 1.0.0** von pearlxcore
(<https://github.com/pearlxcore/OrbisPkgTool>), Commit
`5cd42a515dc29a453c7abcb93318493bdb5b5e1f`, lizenziert unter der **MIT-Lizenz**
(Text in `LICENSE`). Es ist dieselbe Bibliothek, auf der das PS4 PKG Tool von
pearlxcore (GPL-3.0) aufsetzt; hier liegt nur die Befehlszeile, nicht dessen
Oberfläche, und von dem GPL-Programm ist **kein Code** übernommen.

Das Programm braucht dieses Werkzeug für „PS4 PKG → OTA“: PS4-Pakete lesen,
auflisten, entpacken, prüfen, zusammenführen, neu packen und aus einem
Spielordner bauen. Es läuft als eigener Prozess (`ps5_validator/utils/orbispkg.py`);
eine .NET-Laufzeit muss der Anwender nicht installieren, die Datei ist
eigenständig.

## Was hier liegt

| Datei | Inhalt |
|---|---|
| `win-x64/OrbisPkgTool.exe` | die gebaute, eigenständige und getrimmte Befehlszeile (12,8 MB) |
| `pruefsummen.json` | Herkunft, Bauparameter und SHA-256 der Datei |
| `patch/Program.cs.diff` | die eine Änderung am Quelltext |
| `LICENSE` | MIT-Lizenz von pearlxcore |

**Nur Windows (x64).** Für Linux und macOS gibt es keinen Bau; dort fehlt das
Werkzeug, und „PS4 PKG → OTA“ sagt das, statt still nichts zu tun. Entpacken
nimmt in diesem Fall den bisherigen Weg (`ps4_pkg_extract` des PS4 FFPFSC), das
Senden an die Konsole, Umbenennen, Ordnen und die Update-Abfrage brauchen das
Werkzeug nicht.

## Die eine Änderung am Quelltext

`OrbisPkgTool/Program.cs` stellt Standardausgabe und Fehlerausgabe auf UTF-8.
Ohne das schriebe .NET, wenn ein anderes Programm die Ausgabe umlenkt, in der
OEM-Codepage der Konsole – Dateinamen mit Umlauten kämen verfälscht an. Die
rohen Datenströme werden umhüllt (`Console.SetOut`/`SetError`); `Console.OutputEncoding`
zu setzen scheitert, wenn der Prozess keine Konsole hat. Der Unterschied steht in
`patch/Program.cs.diff`.

## So wurde gebaut

Quelle: `OrbisPkgTool-5cd42a5.zip` (GitHub-Archiv des Commits, 248 616 Byte,
SHA-256 `579e7e14f31b52f82cc999504adad6ef8bcbe3b0dc5ea3c3ae6f7ce194fc6c51`),
entpackt, die Änderung aus `patch/Program.cs.diff` angewendet, dann mit dem
.NET-SDK 10.0.401:

```
dotnet publish OrbisPkgTool/OrbisPkgTool.csproj -c Release -r win-x64 --self-contained true ^
  -p:PublishSingleFile=true -p:EnableCompressionInSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true ^
  -p:DebugType=none -p:DebugSymbols=false -p:InvariantGlobalization=true ^
  -p:PublishTrimmed=true -p:TrimMode=partial -p:SuppressTrimAnalysisWarnings=true ^
  -p:JsonSerializerIsReflectionEnabledByDefault=true -o <Ziel> -m:1 --disable-build-servers
```

Zwei Stellen, an denen man sich verrechnet:

* **`JsonSerializerIsReflectionEnabledByDefault=true` ist nötig.** Ohne die Angabe
  trimmt der Linker die JSON-Reflexion weg, und `repack` bricht mit „Reflection-based
  serialization has been disabled“ ab. `info`, `list`, `extract` und `merge`
  merken es nicht – nur `repack`.
* **Vor dem Bauen `bin/` und `obj/` löschen.** Reste eines früheren Bauversuchs
  (ILLink) brachten den Fehler oben trotz gesetzter Angabe zurück.

## Befehle und Ausgabe

`info`, `list`, `extract`, `entries`, `validate`, `verify`, `sweep`, `gp4gen`,
`build`, `repack`, `merge`, `sfo`, `trp` (Aufruf ohne Argumente listet sie).
Der Fortschritt eines Entpackens oder Baus überschreibt dieselbe Zeile mit `\r`
(`[ 83%] 31/37  datei`); `ps5_validator/utils/orbispkg.py` teilt an `\r` und `\n`.
Pakete aus diesem Werkzeug sind **Fake-Pakete**: Der Passcode besteht aus 32
Nullen, die Schlüssel stecken in der Bibliothek.

## Gemessen am 05.10.2026

* `info`, `list` und `extract` an einem echten Paket (Mario Kart 64 [PS2toPS4]):
  `extract` stimmt mit dem Entpacker des PS4 FFPFSC überein (36 von 37 Dateien
  byteweise gleich, nur `license.info` anders).
* `validate` (8 Stufen) lehnt dasselbe, einwandfrei entpackbare Paket an Stufe 3
  (PFSC) ab, `verify` besteht – `validate` ist deshalb nur ein Hinweis, kein Urteil.
* `sfo create --category gp` setzt die Kategorie nicht; sie lässt sich nachträglich
  mit `sfo set CATEGORY gp` setzen. Das Programm legt keine `param.sfo` an: Beim
  Bauen nimmt es die des Spielordners (`gp4gen`, bei einem Patch mit `--patch`).
* Dateinamen mit Umlauten werden im Paket zu `?`.
* `build`, `repack` und `merge` sind an **selbst gebauten Minipaketen** geprüft, nicht
  an einer PS4. Ein Spiel zusammenzuführen oder neu zu packen ist ein Versuch,
  dessen Ergebnis nur die Konsole beurteilt.

## Aktualisieren

1. Neuen Commit (oder neue Freigabe) als ZIP laden, SHA-256 notieren.
2. Die Änderung aus `patch/Program.cs.diff` erneut anwenden – steht sie schon im
   Original, entfällt sie.
3. Mit den Parametern oben bauen (`bin/`, `obj/` vorher löschen).
4. `pruefsummen.json` (Fassung, Commit, SHA-256, Größe) und diese Datei nachführen,
   den Ordner und `WERKZEUGORDNER` in `ps5_validator/utils/orbispkg.py` umbenennen
   (die Fassung steht im Ordnernamen), die Testreihe laufen lassen.
