# Benutzerhandbuch

## Uebersicht

Dieses Programm ist ein Windows-Desktop-Tool zum Konvertieren, Packen, Entpacken und Pruefen von PS5-Dump-Formaten.

## Voraussetzungen

- Windows
- Python 3.10 oder neuer, falls du die `.py`-Version startest
- Genug freien Speicherplatz fuer Zwischen- und Ausgabedateien
- Administratorrechte fuer Aufgaben mit exFAT-Mounts

## Programm starten

### Python-Version

```powershell
python PS5ImageConverter_Pro_FINAL_revised.py
```

### EXE-Version

Die EXE kann per Doppelklick oder ueber das Build-Ergebnis gestartet werden.

## So benutzt du das Programm

1. Programm starten
2. Gewuenschte Aufgabe auswaehlen
3. Quelldatei oder Quellordner waehlen
4. Zielordner festlegen
5. Start klicken
6. Auf die Fertig-Meldung warten

## Die 8 Aufgaben

1. Game Dump Ordner -> `ffpfsc`
2. `ffpfsc` -> `exFAT`
3. `exFAT` -> `ffpfsc`
4. `ffpfsc` -> Game Dump Ordner
5. `exFAT` -> Game Dump Ordner
6. `ffpkg` -> `ffpfsc`
7. `fakelib` verwalten
8. Dump Validator

## Wichtige Hinweise

- Aufgaben 1, 2, 4 und 5 koennen Administratorrechte benoetigen.
- Wenn Windows eine UAC-Abfrage zeigt, mit Ja bestaetigen.
- Bei exFAT-Aufgaben muss OSFMount installiert und nutzbar sein.
- Der Dump Validator prueft, ob ein Dump vollstaendig und plausibel ist.

## Hilfsmenu Ressourcen

Im Ressourcen-Bereich koennen benoetigte Helfer automatisch installiert werden:

- OSFMount
- Dokan2
- FileZilla

Bereits installierte Tools werden nicht erneut installiert.

## Typische Arbeitsablaeufe

### Dump in ffpfsc umwandeln

1. Aufgabe 1 waehlen
2. Dump-Ordner waehlen
3. Zielordner waehlen
4. Start klicken

### ffpfsc wieder entpacken

1. Aufgabe 4 waehlen
2. `ffpfsc`-Datei waehlen
3. Zielordner waehlen
4. Start klicken

### Dump pruefen

1. Aufgabe 8 waehlen
2. Dump-Ordner waehlen
3. Start klicken
4. Bericht lesen

## Speicherorte

- Einstellungen und Pfade werden unter Windows in der Regel in `APPDATA` gespeichert.
- E2E-Reports und Zwischenartefakte landen im jeweiligen `_e2e_output_...`-Ordner.

## Fehlerbehebung

- Programm startet nicht: Direkt per Python starten und die Ausgabe lesen.
- UAC erscheint: Admin-Rechte bestaetigen.
- OSFMount-Fehler: Pruefen, ob das Tool installiert ist und ob genug Rechte vorhanden sind.
- Falsche Datei gewaehlt: Endung und Quelle noch einmal pruefen.
- Dump Validator faellt durch: Fehlende oder kaputte Dateien im Dump suchen.

## Kurz-Tipp

Wenn du dir unsicher bist, starte mit Aufgabe 8. Der Validator zeigt oft schnell, ob ein Dump grundsaetzlich in Ordnung ist.