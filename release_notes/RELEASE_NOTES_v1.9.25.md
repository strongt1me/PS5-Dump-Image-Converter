# PS5 Dump & Image Converter v1.9.25

Ein vollständiger Durchgang durch das ganze Programm. Jeder Verdacht wurde
nachgemessen, behoben und mit einem Wächtertest festgehalten, der ohne die
Reparatur rot wird. Die wichtigste Entdeckung betrifft Abbilder mit
AMPR-EMU-Asset-Pack.

## Asset-Pack: der Index wurde beim Packen heimlich neu gebaut

Bei der neuen Methode des AMPR EMU wandern die Spieldateien in gepackte
Bänder. Deren Manifest beruft sich auf die Satznummern aus `ampr_emu.index`.
Beim anschließenden Packen der `.ffpfsc`/`.ffpfs` hat die Engine diesen Index
**noch einmal** neu erzeugt – still, und ohne dass eine Prüfung angeschlagen
hätte.

Im fertigen Abbild zeigte danach jede Nummer auf eine andere Datei. An einem
echten Spiel gemessen: 79 Index-Sätze gegen 72 Dateien im Manifest, **alle 72
falsch zugeordnet** – und das Protokoll meldete „Erfolgreich abgeschlossen".
Auf der Konsole führt das zu Ladefehlern oder zu einem Spiel, das nicht
startet.

Jetzt entscheidet allein das Programm über den Index. **Abbilder mit
Asset-Pack einmal neu bauen** – `.ffpkg` und `.exFAT` waren nie betroffen.

## Der Weg folgt jetzt der Anleitung des Entwicklers

Neu beim Bau der Bänder: die vollständige Dateiliste des Manifests wird
gelesen und jede lose gebliebene Datei muss wirklich vorhanden sein; Manifest,
Index und Zwischenspeicher werden gegen den festen Speicherblock der Konsole
gerechnet; die Prüfsummenbeilage `.crc` kommt mit ins Abbild; übernommen
werden nur die vom Manifest genannten Bänder, und danach wird nachgezählt. Ein
Profil aus einem abgebrochenen Lauf wird nicht mehr weiterbenutzt, der
Ausgabeordner bleibt nicht mehr liegen, und Bibliotheken, Laufzeitprotokolle
und der PlayGo-Zwischenspeicher wandern nicht mehr in die Bänder.

Der Indexbauer arbeitet Byte für Byte wie das Skript des Entwicklers. Vorher
waren Pfade mit Umlauten oder japanischen Zeichen falsch eingeordnet.

## Gepackte Originale weglassen

Beim Start mit Asset-Pack fragt das Programm einmal, ob die gepackten
Originaldateien im Ergebnis weggelassen werden sollen. Vorgabe ist **Nein**,
entfernt wird nur in der Arbeitskopie. Platz spart das bei `.ffpfs`, `.exFAT`
und `.ffpkg`; eine `.ffpfsc` wird dadurch nicht kleiner. Erst mit Originalen
bauen und auf der Konsole durchspielen, dann ohne.

## Aufgabe 7 ist wieder nur der AMPR EMU Manager

Aufgabe 7 baut keine Bänder mehr und entfernt auch keine; ein vorhandenes
Asset-Pack bleibt unangetastet. Bänder entstehen nur beim Erstellen eines
Abbilds. Der Knopf „Asset-Pack entfernen" ist entfallen – er löschte Manifest
und Bänder in der Annahme, die Originale lägen daneben.

## PlayGo und frühere Einbauten

Erklärt ein Spiel PlayGo-Inhalte und ist der Stub nicht angehakt, sagen das
Vorabprüfung und Protokoll; eingebaut wird er weiterhin nur auf Wunsch.
Enthält der Quellordner bereits AMPR-Bibliothek, PlayGo-Stub,
Backport-Bibliotheken oder ein Asset-Pack aus einem früheren Lauf, wird das
vor dem Start gemeldet – die Kästchen legen nur etwas dazu, sie nehmen nichts
heraus.

## OSFMount wird nicht mehr verlangt

`.exFAT`-Abbilder liest das Programm mit seinem eingebetteten Leser – ohne
Einhängen, ohne Administratorrechte, auf jedem Betriebssystem. OSFMount ist
nur noch der Rückfall für ein ungewöhnlich aufgebautes Abbild und kann bei
Bedarf aus dem Programm heraus installiert werden.

## Mitgelieferte Fremdwerkzeuge auf neuestem Stand

ShadowMount+ 1.7alpha13fix1, elfldr 0.26, PS5Upload 5.28.0, PS5 Game
Compressor 1.0.4, PS5 Web File Manager 1.9, GarlicSaves 1.13, PIZZA-HEN 2.00,
ftpsrv 0.21.1, PS4 FFPFSC 0.2.9. UFS2Tool ist auf .NET 10 neu gebaut – die
bisherige .NET-8-Laufzeit bekommt ab dem 10.11.2026 keine
Sicherheitskorrekturen mehr.

## Neue Prüfung: Werkzeugpflege

Der Diagnosebericht hält die mitgelieferten Payloads gegen ihre Auflistung in
der Lizenzdatei, in beide Richtungen, und nennt die Fassung selbst
installierter Fremdwerkzeuge. `--werkzeuge-pruefen` sieht auf ausdrücklichen
Befehl nach neueren Fassungen; das ist der einzige Netzzugriff dieses Laufs.

## Abbrechen, Fenster, Anzeige

„Abbrechen" wirkt jetzt auch beim Auspacken einer `.exFAT`, beim Prüfen der
Bänder, beim `.ffpkg`-Bau und beim BACKPORT – ohne dass das Fenster einfriert
oder ein halbes Ergebnis liegen bleibt. Lange Messungen laufen im Hintergrund,
der Fortschrittsbalken springt nicht mehr und bleibt nicht bei 98 % stehen,
Menüs klappen unter Linux wieder auf, und das Mausrad reagiert auf Touchpads
und unter macOS.

## Weitere Behebungen

Das Aufräumen beim Beenden konnte fertige Ergebnisse löschen. Aufgabe 8 hielt
abgeschnittene Abbilder für bestanden, die Inspektion meldete Erfolg auch ohne
jede lesbare Angabe. Die Quellvorschau packte flache `.ffpfs` vollständig aus.
„Abbild → PKG" rechnete den Platzbedarf mit der Dateigröße statt mit dem
entpackten Dump. Das Mac-Bündel veränderte UFS2Tool beim Signieren, wodurch
`.ffpkg` dort unbrauchbar war. Gebaute Linux- und Mac-Fassungen finden ihre
Zertifikate wieder.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.25.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.25_linux_x86_64` – nach dem Download ausführbar machen:

  ```
  chmod +x PS5_Dump_Image_Converter_v1.9.25_linux_x86_64
  ```

- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.25.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.
