# PS5 Dump & Image Converter v1.9.32

Filme blieben trotz Ausschlussliste im Band. Ursache: Groß- und
Kleinschreibung.

## Was war

Beim Prüfen der Reparatur aus v1.9.31 an einem echten Spiel („Wer wird
Millionär") fiel auf: Alle 17 Filme lagen im Band, obwohl `movies/**` in der
Ausschlussliste steht. Der Ordner heißt dort
`Media/StreamingAssets/`**`Movies`**`/` – mit großem M. Das Packwerkzeug
vergleicht Muster mit `fnmatch.fnmatchcase`, also **schreibungsgenau**;
`movies` trifft `Movies` nicht.

## Was jetzt gilt

Das Programm liest die Film- und Videoordner (`movie`, `movies`, `video`,
`videos` – in jeder Schreibung) **aus dem Spielordner** und schließt sie in
genau der dort vorhandenen Schreibweise aus. Dasselbe gilt für die
Systemdateien: `playgo.pgm`, `*.packman` und die `pgc_*`-Dateien werden
ebenfalls im Ordner gesucht, damit auch ein Spiel mit `PlayGo.pgm` richtig
gepackt wird, statt den Bau am Riegel aus v1.9.31 anzuhalten.

Nachgemessen am selben Spiel, mit `ampr_pack.py list --json` des Entwicklers
als Prüfer:

| | gepackt | lose | Filme im Band |
| --- | --- | --- | --- |
| vorher | 214 | 45 | 17 von 17 |
| jetzt | 197 | 62 | **0 von 17** |

Landet trotzdem ein Video in einem Band – etwa mit einem eigenen Packprofil –,
sagt es das Programm im Protokoll. Abgebrochen wird deswegen nicht: Belegt ist
nur, dass alle veröffentlichten Profile Filme lose lassen (Ghost of Yotei
`movies/**`, FF7 Rebirth `end/content/movie/**`, Spider-Man 2 `d/movie`, Astro
Bot `data/prein/video/*`), nicht dass ein gepacktes Video ein Spiel anhält.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.32.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.32_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.32_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.32.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
