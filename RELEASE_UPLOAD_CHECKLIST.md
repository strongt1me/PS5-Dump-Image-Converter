# Release Upload Checklist

## Vor dem Upload

- EXE frisch ueber `Build_EXE.ps1` bauen
- EXE einmal lokal starten
- Datei-Details der EXE pruefen (`FileVersion`, `ProductVersion`, `FileDescription`)
- SHA-256 fuer das Release notieren
- Release Notes aktualisieren oder pruefen

## Beim Upload

- EXE direkt aus dem `dist/`-Ordner hochladen
- Versionsnummer im Release-Titel und Dateinamen abgleichen
- SHA-256 im Release-Text mit angeben
- Kurz erwaehnen, dass die EXE derzeit nicht digital signiert ist

## SmartScreen / Antivirus

- Nach dem Upload mit derselben unveraenderten EXE arbeiten, nicht mehrfach neu packen
- Falls Defender oder SmartScreen anschlaegt, die EXE als False Positive einreichen
- GitHub als feste Download-Quelle nutzen statt wechselnder Mirrors
- UPX deaktiviert lassen, um unnoetige False Positives eher zu reduzieren

## Nach dem Upload

- Download der veroeffentlichten EXE einmal selbst testen
- SHA-256 des Downloads gegen den lokalen Build pruefen
- Kurz pruefen, ob SmartScreen/Defender eine Warnung ausgibt
- Bei Problemen Release-Notiz um Known Issues oder AV-Hinweise erweitern