# PS5 Dump & Image Converter v1.9.38

Gepackte Originaldateien werden nicht mehr entfernt, solange das Packprofil
vom Programm stammt. Eine Sicherung, die auf Engine-Erkennung baute, hat an
der Konsole nicht gehalten.

## Was gemessen wurde

`Arkanoid – Eternal Battle` ist **kein** Unity-Titel. Die Engine-Erkennung
fand nichts, das Programm ließ die gepackten Originaldateien entfernen – und
das Abbild **stürzte an der Konsole ab**. Dieselbe Quelle, dieselben Bänder,
aber mit den Originalen daneben: läuft.

| | ohne Originale |
| --- | --- |
| Ghost of Yotei | SIGSEGV 0,2 s nach EMU-Start |
| Arkanoid – Eternal Battle | stürzt ab |

Zwei von zwei. Und bis heute hat **kein** Titel gezeigt, dass die Bänder
überhaupt gelesen werden.

Beim Nachsehen fanden sich in Arkanoid `.gnf`-Texturatlanten bis 357 MB und
zehn FMOD-`.bank`-Dateien. FMOD liest über eigene Datei-Rückrufe, große
Atlanten werden eingeblendet – beides läuft am AMPR EMU vorbei. Die Erkennung
kannte fünf Unity-Dateinamen.

## Was sich ändert

Solange das Packprofil vom Programm stammt, bleiben die gepackten
Originaldateien **immer** stehen – auch bei gewählter Option „Originale
weglassen“. Eine Aufzählung von Engines kann das nicht sichern: Sie müsste
jede künftige schon kennen, und der Fehlschlag trifft den Anwender erst an
der Konsole.

Die Erkennung bleibt und sperrt nicht mehr, sondern **erklärt**: Bei Unity
nennt das Protokoll den Namen und die gefundenen Dateien, sonst steht die
allgemeine Begründung mit dem Arkanoid-Beleg dort.

## Der Weg ohne Originale bleibt offen

Über ein eigenes Packprofil aus Konsolen-Mitschnitten –
`<Name des Dump-Ordners>_ampr_pack.toml` neben den Dump-Ordner. Daran hat
sich nichts geändert: Wer aus Mitschnitten packt, weiß, was der Titel über
APR liest.

**Praktische Folge:** Ein Abbild mit Asset-Pack wird über den normalen Weg
nicht kleiner als die Quelle, sondern größer. Der Gewinn an Dateizahl bleibt
– bei Arkanoid 1167 lose Dateien gegenüber 32 plus vier Bändern –, die
Ersparnis an Platz nicht.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.38.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.38_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.38_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.38.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
