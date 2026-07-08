# Release Upload Checklist

## Vor dem Upload

- EXE frisch über `Build_EXE.ps1` bauen
- EXE einmal lokal starten
- Datei-Details der EXE prüfen (`FileVersion`, `ProductVersion`, `FileDescription`)
- SHA-256 für das Release notieren
- Release Notes aktualisieren oder prüfen

## Beim Upload

- EXE direkt aus dem `dist/`-Ordner hochladen
- Versionsnummer im Release-Titel und Dateinamen abgleichen
- SHA-256 im Release-Text mit angeben
- Kurz erwähnen, dass die EXE derzeit nicht digital signiert ist

## SmartScreen / Antivirus

- Nach dem Upload mit derselben unveränderten EXE arbeiten, nicht mehrfach neu packen
- Falls Defender oder SmartScreen anschlägt, die EXE als False Positive einreichen
- GitHub als feste Download-Quelle nutzen statt wechselnder Mirrors
- UPX deaktiviert lassen, um unnötige False Positives eher zu reduzieren

## Nach dem Upload

- Download der veröffentlichten EXE einmal selbst testen
- SHA-256 des Downloads gegen den lokalen Build prüfen
- Kurz prüfen, ob SmartScreen/Defender eine Warnung ausgibt
- Bei Problemen Release-Notiz um Known Issues oder AV-Hinweise erweitern
