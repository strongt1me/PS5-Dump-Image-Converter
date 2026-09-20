# PS5 Dump & Image Converter v1.9.33

Ein Abbild ohne Originale startete bei manchen Spielen nicht. Die Ursache
liegt nicht im Pack, sondern darin, **wie** ein Spiel seine Daten liest.

## Die Bänder bedienen nur Lesevorgänge über APR

Was eine Spiel-Engine mit gewöhnlichem Datei-Zugriff holt, muss als richtige
Datei im Abbild liegen – nach „Originale weglassen“ ist es sonst schlicht
weg.

An der Konsole gemessen: ein Unity-Spiel, ohne Originale gebaut, mit dem
Debug-Bau des AMPR EMU 0.4.2.1. Der Emulator meldete für fünf Dateien der
Unity-Laufzeit `io.hook.error … No such file or directory` (12× `stat`,
7× `open`, 6× `sceKernelClose`) – er hat sie also **nicht** aus den Bändern
bedient. Im ganzen Mitschnitt stand **keine einzige** `apr.pack`-Zeile, und
das Spiel beendete sich kurz nach dem Start
(`SYSTEM_ABNORMAL_TERMINATION_REQUEST`). Dasselbe Spiel mit denselben Bändern
**und** den Originalen daneben lief durch.

## Was jetzt gilt

Das Programm erkennt solche Titel an ihren Laufzeitdateien – `data.unity3d`,
`globalgamemanagers`, `global-metadata.dat`, `ScriptingAssemblies.json`,
`RuntimeInitializeOnLoads.json` – und **lässt die gepackten Originale
stehen**, auch wenn das Weglassen gewählt wurde. Im Protokoll steht, was
gefunden wurde und warum. Das Abbild wird dadurch nicht kleiner, aber es
startet.

Von 31 echten Spiel-Dumps sind 12 solche Titel. Die IL2CPP-Metadaten
(`global-metadata.dat`) wandern außerdem nie mehr in ein Band – so wie schon
die PlayGo-Dateien seit v1.9.31.

Am echten Spiel nachgemessen, beide Fälle mit demselben Dump:

| | Dateien im Abbild | gepackte Originale darin | Größe |
| --- | --- | --- | --- |
| Profil des Programms (Riegel greift) | 79 | 20 von 20 | 167.051.264 B |
| eigenes Profil aus Mitschnitten | 59 | 0 von 20 | 160.038.912 B |

In beiden Fällen führt das Manifest 71 Dateien, davon 20 gepackt und 51 lose,
und jede lose geführte Datei liegt im Abbild.

### Warum nicht einfach alle fünf Dateien vom Packen ausnehmen

In dem Abbild, das abstürzte, waren 197 von 259 Dateien gepackt und entfernt
– vier der fünf Namen waren dabei. Da aber keine einzige `apr.pack`-Zeile im
Mitschnitt steht, ist nicht belegt, dass für diesen Titel überhaupt *eine*
gepackte Datei bedient wurde; die vier sind nur die, an denen es sofort
auffiel. Vier Namen mehr auszuschließen hieße raten, dass die übrigen 193
tragen. Und `data.unity3d` trägt bei vielen Titeln den gesamten Spielinhalt
– lose gelassen bliebe vom Pack ohnehin nichts.

## Ein eigenes Packprofil hat Vorrang

Eine Datei mit dem Namen des Dump-Ordners und der Endung `_ampr_pack.toml`
**neben** dem Dump-Ordner – etwa `Mein Spiel_ampr_pack.toml` neben
`Mein Spiel\` – wird übernommen, nie überschrieben und hält den Bau auch
nicht am Riegel an. Wer aus Konsolen-Mitschnitten packt, weiß selbst, was der
Titel über APR liest.

Bisher war das gar nicht erreichbar: Gepackt wird in einem Ordner neben der
Arbeitskopie, und die liegt in einem frisch erzeugten temporären Ordner.

Wird „weglassen“ gewählt und stammt das Profil vom Programm, steht der
Vorbehalt jetzt gleich beim Bau im Protokoll.

## Wenn der Arbeitsspeicher ausgeht

`MemoryError` trägt keinen Text; die Meldung im Fenster endete deshalb mit
einem Doppelpunkt und nichts dahinter. Jetzt steht dort ein Satz samt dem
tiefsten während des Laufs gemessenen Wert an freiem Arbeitsspeicher.

Zusätzlich warnt die Vorabprüfung, wenn beim Start weniger als 1 GB frei ist:
Bei 0,8 GB brach ein Packlauf in MkPFS ab, nach dem Schließen anderer
Programme lief derselbe Lauf durch.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.33.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.33_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.33_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.33.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
