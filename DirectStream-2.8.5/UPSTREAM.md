# Direct Stream for PlayStation 5 – mitgeliefertes Fremdwerkzeug

Grundlage ist **DIRECT STREAM FOR PLAYSTATION 5, Fassung 2.8.5** von
**ChillQuant** (`https://github.com/ChillQuant/direct-stream-ps5`), lizenziert
unter der **MIT-Lizenz**. Der Lizenztext liegt als `LICENSE` daneben; er selbst
nennt keinen Namen („Copyright (c) 2024-2026“).

Stand: GitHub-Freigabe **v2.8.5** (05.10.2026), Anhang
`DIRECT-STREAM-FOR-PLAYSTATION-5-PurePython.zip`, SHA-256
`5b8136e522009484a338cba651fdb04441580e0541fb9c41f5bd5352e96598d5` – gleich
dem `digest`, den GitHub für den Anhang nennt (am 06.10.2026 gemessen). Vorher
lag 2.8.1 bei; deren Archiv war ebenso byte-gleich mit der Freigabe v2.8.1.

## Unverändert

Alle elf Dateien des Werkzeugs sind byte-gleich mit dem Quellarchiv;
`herkunft.json` nennt die Prüfsumme jeder Datei, `test_direct_stream.py` hält
den Ordner dagegen. Nicht übernommen: `tests/` (braucht `pyftpdlib` und würde
von `pytest` im Projektstamm eingesammelt), `requirements-dev.txt`,
`.gitignore` und die Android-Skripte (`run_android.sh`, `install_android.sh`).

Eigene Beigaben: diese Datei, `herkunft.json` und
`entwickler_chillquant.png` – das GitHub-Profilbild des Entwicklers (das
automatisch erzeugte Muster von GitHub), gezeigt in der Kopfzeile neben Name
und GitHub-Link.

## Was es ist

Ein kleiner Webserver aus der Python-Standardbibliothek mit einer Oberfläche
aus HTML und JavaScript. Er holt HTTP/HTTPS-Downloads mit mehreren
Bereichsabfragen gleichzeitig (1 bis 32 Ströme) und schickt sie über FTP
**direkt** in den Speicher der Konsole, ohne die Datei vorher auf der Platte
abzulegen. Dazu: lokale Dateien hochladen, eine Warteschlange mit Pause und
Fortsetzen (unvollständige Dateien heißen `….ps5part`, umbenannt wird erst nach
bestätigter Größe), ein Geschwindigkeitstest, ein Dateibrowser für den Speicher
der Konsole.

## Wie das Programm es einbindet

- Knopf **8. Direct Stream** in der Ansicht KONSOLE. Er startet den Server im
  Programm selbst (`ps5_validator/utils/direct_stream.py`) – nur auf
  `127.0.0.1`, mit eigener Sitzungsmarke – und zeigt seine Seite rechts.
- **Kein `main()`.** Das Programm lädt `transfer_core.py` und
  `ps5_streamer.py` aus der Datei und baut den Server wie `main()`.
- **Sprache und neutrale Texte.** Die Oberfläche des Werkzeugs ist englisch und
  spricht vom Mac. Das Programm ändert dafür **keine Datei**: Es liefert die
  Seite mit einem zusätzlichen Skript (`/ps5conv-texte.js`) aus, das die Texte
  im Browser ersetzt – auf Deutsch, wenn das Programm deutsch eingestellt ist,
  sonst die englischen Texte mit „computer“ statt „Mac“. Wörterbuch und Regeln
  stehen in `ps5_validator/utils/direct_stream_texte.py`.
- **Datenordner:** `DirectStream/` im Einstellungsordner des Programms
  (`state.json`). Beim ersten Start trägt das Programm die PS5-Adresse, den
  FTP-Port und als Zielordner `/data/homebrew` ein (dort sucht ShadowMount+
  immer); was auf der Seite gespeichert wurde, bleibt unberührt.
- Der Server läuft weiter, wenn man die Seite verlässt, und endet mit dem
  Programm; läuft dann gerade ein Auftrag, fragt das Programm vorher.

## Nicht geprüft

Das Verhalten der FTP-Gegenseite an der Konsole – `SIZE`, `REST`, `STOR`,
Umbenennen, freier Platz – ist an der echten PS5 mit einer kleinen Datei zu
erproben, bevor große Titel übertragen werden.

## Aktualisieren

Freigabe-Anhang laden, Prüfsumme gegen den `digest` der GitHub-API halten,
Ordner durch die neue Fassung ersetzen (neuer Ordnername mit Fassung),
`herkunft.json` neu erzeugen, `direct_stream.ORDNER` und die drei `.spec`
anpassen und `test_direct_stream.py` laufen lassen. Danach mit
`test_direct_stream_texte.py` prüfen, welche Texte der neuen Oberfläche noch
keine Übersetzung haben.
