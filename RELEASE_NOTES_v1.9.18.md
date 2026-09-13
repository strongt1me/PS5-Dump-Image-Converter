Aufgabe 4 packt eine `.ffpkg` jetzt auch dann korrekt aus, wenn darin eine
Datei größer als 2 GB liegt – und eine Kleinigkeit im Kommandozeilen-Fenster.

## `.ffpkg` mit Dateien über 2 GB

Bisher scheiterte **Aufgabe 4** (`.ffpkg` → Dump-Ordner oder `.exFAT`), sobald
das Paket eine **einzelne Datei größer als 2 GB** enthielt – und viele große
Spiele haben genau das. Der Vorgang brach mit einer kryptischen Meldung ab
(`robocopy rc=9`, dann „Unzulässige Funktion").

Ursache lag im eingebetteten **UFS2Tool**: Es las jede Datei komplett in den
Speicher und war dabei auf 2 GB (int32) begrenzt. UFS2Tool ist hier deshalb
**gepatcht** – es schreibt die Dateien jetzt streamend heraus, ohne
Größenlimit. Für Dateien über 2 GB nutzt das Programm den mount-freien
`extract`-Weg.

Geprüft an einem echten Spiel (`Double Dragon Revive`, eine 6,8-GB-Datei):
Das ausgepackte Paket ist **byte-genau** identisch zum Original (51 Dateien,
10,64 GB). Der Weg von `.ffpkg` nach `.ffpfsc` war nie betroffen und bleibt
unverändert.

Die geänderte UFS2Tool-Quelle und eine Beschreibung liegen dem Programm in
`UFS2Tool-4.1/patch/` bei; die Laufzeit prüft die vier Plattform-Binärdateien
gegen `UFS2Tool-4.1/pruefsummen.json`.

## Kommandozeile

Das Fortschritts-Fenster des `--cli`-Modus zeigte in der Konfig-Anzeige immer
die Standard-Aufgabe – samt „BAUFORM"-Auswahl –, egal welche Aufgabe wirklich
lief. Jetzt gleicht das Fenster Kopf, Zielformat-Optionen und die
„BAUFORM"-Sichtbarkeit an die tatsächlich laufende Aufgabe an.

## Dateien

| Datei | Plattform |
| --- | --- |
| `PS5_Dump_Image_Converter_v1.9.18.exe` | Windows 64-bit |
| `SOURCE_FILE_MANIFEST_v1.9.18.sha256` | Prüfsummen der Quelldateien |

Die Programmdatei läuft eigenständig; es muss nichts nachinstalliert werden.
