# libs – eigene Bibliotheken

Dieser Ordner ist für **selbst gebaute Bibliotheken**, die das mitgelieferte
Werkzeug zum PKG-Bauen ersetzen sollen. Er ist im Auslieferungszustand leer –
dann arbeitet das Programm wie bisher mit dem mitgelieferten
`ProsperoPkg-2.5`.

## So wird er benutzt

Datei hier hineinlegen. Mehr nicht. Beim nächsten PKG-Bau nimmt das Programm
sie von selbst.

Beachtet werden genau diese Namen:

| Datei | Art | Gilt auf |
|---|---|---|
| `LibProsperoPkg.dll` | .NET-Assembly | Windows, Linux, macOS |
| `libScePubTools.dll` | native Bibliothek | Windows |
| `libScePubTools.so` | native Bibliothek | Linux |
| `libScePubTools.dylib` | native Bibliothek | macOS |

Eine .NET-Assembly heißt auf **jeder** Plattform `.dll` – auch unter Linux und
macOS. Nur die native Bibliothek trägt dort eine andere Endung. Die
Windows-Schreibweise `libScePubTools.dll` wird überall zusätzlich akzeptiert.

Eine Datei mit 0 Byte wird ignoriert – das ist ein Versehen, kein Ersatz.

Zur `LibProsperoPkg.dll` dürfen `LibProsperoPkg.pdb` und
`LibProsperoPkg.xml` danebenliegen: Sie wandern automatisch mit, **wenn die
DLL da ist**. Allein bewirken sie nichts. Ohne die `.pdb` nennt .NET in einem
Absturzbericht keine Zeilennummern – wer selbst baut, will genau die sehen.

## Unterordner werden nicht benutzt

Gesucht wird nur in der **obersten Ebene**. Ein Unterordner – etwa ein
kompletter SDK-Baukasten unter `libs/sdk/` mit `prospero-pub-cmd.exe`,
`toolchain/ext/` und eigenen Skripten – bleibt liegen und bewirkt nichts.

Das ist kein Versehen: Solche Werkzeugketten sind **ein anderes Programm**,
kein Austausch einer Bibliothek. Sie zu benutzen wäre ein zweiter Bauweg
(bauen über die Publishing Tools statt über `prosperopkg`) – der ist nicht
gebaut. Damit niemand vergeblich auf eine Wirkung wartet, nennt der
Diagnosebericht einen solchen Ordner ausdrücklich als *„liegt da, wird aber
nicht benutzt"*.

## Wo der Ordner liegen muss

* **Windows und Linux:** neben der Programmdatei (im Bündel liegt er schon
  dabei).
* **macOS:** **neben** der `.app`, nicht hinein. In das Bündel gehört er
  nicht: `Contents/Resources` ist beim Signieren versiegelt – eine dort
  abgelegte Datei macht das Bündel ungültig („a sealed resource is missing
  or invalid"), und auf Apple Silicon startet es dann gar nicht mehr.
* **Aus dem Quelltext heraus:** im Projektordner (also genau hier).

## Die Fassung muss passen – sonst lädt .NET sie nicht

Die mitgelieferte Hülle `prosperopkg.dll` ist fest gegen
**`LibProsperoPkg, Version=2.6.0.0`** (.NET 10) gebunden; das steht in
`ProsperoPkg-2.5/<plattform>/prosperopkg.deps.json`. .NET lädt eine Assembly
nur, wenn **Name und Version** übereinstimmen. Eine Datei mit einer anderen
Assembly-Version wird abgelehnt – egal wie gut sie ist:

```
[FEHLER] FileNotFoundException: Could not load file or assembly
'LibProsperoPkg, Version=2.6.0.0, Culture=neutral, PublicKeyToken=null'
```

Am 23.09.2026 genau so gemessen mit einer `LibProsperoPkg.dll` der Fassung
**1.2.0.0** (für .NET 9): Der Tausch griff, und danach scheiterte jeder
Aufruf.

**Deshalb prüft das Programm die Kopie, bevor es sie benutzt.** Es ruft das
Werkzeug einmal mit `read` auf eine nicht vorhandene Datei auf – das zwingt
.NET, die Bibliothek zu laden. Klappt das nicht, wird die Kopie verworfen,
es läuft weiter das mitgelieferte Werkzeug, und der Diagnosebericht nennt
den Grund. Ein Aufruf ohne Argumente genügt dafür übrigens **nicht**: .NET
lädt eine Assembly erst, wenn sie gebraucht wird.

Wer eine Bibliothek eines anderen Zweigs benutzen will (etwa 1.2.0 wegen
`ExtractInnerFiles`), muss die Hülle selbst gegen diesen Zweig neu bauen –
ein Umbenennen der Datei genügt nicht.

## Was dabei passiert

Das Programm überschreibt **nichts** im mitgelieferten Werkzeugordner. Es legt
stattdessen eine Arbeitskopie im Einstellungsordner an
(`prosperopkg_eigen`), legt Ihre Datei dort darüber und startet aus der Kopie.

Daraus folgt zweierlei:

* Nehmen Sie die Datei hier wieder heraus, arbeitet das Programm beim nächsten
  Lauf wieder mit dem mitgelieferten Werkzeug – ohne weiteres Zutun.
* Tauschen Sie die Datei gegen eine neuere, wird die Arbeitskopie automatisch
  neu angelegt. Erkannt wird das an der Prüfsumme, nicht am Datum.

Der Diagnosebericht zeigt unter **Eigene Bibliotheken**, welche Datei gerade
gilt, wie groß sie ist und welche SHA-256 sie hat. Steht dort nichts, läuft
das mitgelieferte Werkzeug.

## Wichtig

* Die Dateien hier werden **nicht** mit ins Git aufgenommen (siehe
  `.gitignore`) – es sind Ihre eigenen Bauten, und fremde Binärdateien haben
  im Projekt ohnehin nichts verloren.
* Eine eigene `libScePubTools.dll` ersetzt eine Sony-Bibliothek. Legen Sie hier
  **nur selbst gebaute** Dateien ab, keine aus fremden Paketen entnommenen.
  Dateien aus dem offiziellen SDK – `libScePubTools.dll`,
  `prospero-pub-cmd.exe`, `da/fa/p2d/ric/sc2.exe`, `ispc_texcomp.dll`,
  `libatrac9.dll` – gehören Sony. Sie dürfen hier lokal liegen, aber **nie
  weitergegeben werden**: nicht ins Git (dafür sorgt die `.gitignore`), nicht
  ins Bündel, nicht in ein Release.
* Passt die Bibliothek nicht zur erwarteten Schnittstelle, scheitert der Bau
  mit der Meldung des Werkzeugs. Das Programm prüft den Inhalt nicht – es kann
  nicht wissen, was Ihre Fassung können soll.
