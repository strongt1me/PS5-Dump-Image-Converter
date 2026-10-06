# Direct Stream for PlayStation 5 – mitgeliefertes Fremdwerkzeug

Grundlage ist **DIRECT STREAM FOR PLAYSTATION 5, Fassung 2.8.1**, lizenziert
unter der **MIT-Lizenz**. Der Lizenztext liegt als `LICENSE` daneben; er nennt
keinen Urheber („Copyright (c) 2024-2026“). Eine öffentliche Quelle ist nicht
bekannt.

Stand: Archiv `DIRECT-STREAM-FOR-PLAYSTATION-5-PurePython.zip` (SHA-256
`f5167b0cd47be228b6f70c8c93c680f91a06034c988db3708f2d9bfecfd8992b`), am
05.10.2026 vom Projektinhaber bereitgestellt. Dazu lagen vier weitere Archive
vor (Windows, macOS, `direct-stream-ps5-2.8.1.zip` und `.tar.gz`). Gemessen per
SHA-256: `ps5_streamer.py`, `transfer_core.py`, `LICENSE`, `requirements.txt`
und alle vier Dateien in `web/` sind in allen fünf Archiven byte-gleich. Sie
unterscheiden sich nur in den Startskripten (`Launch Direct Stream for
PlayStation 5.bat`, `.app`-Bündel, `.command`), die hier nicht gebraucht werden.

## Unverändert

Alle zehn Dateien (außer dieser und `herkunft.json`) sind byte-gleich mit dem
Quellarchiv. `herkunft.json` nennt die Prüfsumme jeder Datei;
`test_direct_stream.py` hält den Ordner dagegen. Nicht übernommen wurden
`tests/` (braucht `pyftpdlib` und würde von `pytest` im Projektstamm
eingesammelt), `requirements-dev.txt` und `.gitignore`.

## Was es ist

Ein kleiner Webserver aus der Python-Standardbibliothek mit einer Oberfläche
aus HTML und JavaScript. Er holt HTTP/HTTPS-Downloads mit mehreren
Bereichsabfragen gleichzeitig (1 bis 32 Ströme) und schickt sie über FTP
**direkt** in den Speicher der Konsole, ohne die Datei vorher auf der Platte
abzulegen. Dazu: lokale Dateien hochladen, eine Warteschlange mit Pause und
Fortsetzen (unvollständige Dateien heißen `….ps5part`, umbenannt wird erst nach
bestätigter Größe), ein Geschwindigkeitstest, ein Dateibrowser für den Speicher
der Konsole. Es braucht keine Pakete von außen.

Zugriffsschutz des Werkzeugs: Der Server lauscht nur auf `127.0.0.1`, jede
Anfrage der Schnittstelle trägt eine Sitzungsmarke, `Host` und `Origin` werden
geprüft, das FTP-Kennwort bleibt im Arbeitsspeicher.

## Wie das Programm es einbindet

- Knopf **8. Direct Stream** in der Ansicht KONSOLE. Er startet den Server im
  Programm selbst (`ps5_validator/utils/direct_stream.py`) und zeigt seine
  Seite rechts (WebView2 unter Windows, sonst der Browser) – wie die
  Weboberflächen der Konsole, aber ohne Payload: Es läuft nichts auf der PS5.
- **Kein `main()`.** `main()` verlangt, der Prozess zu sein (Sperre für eine
  einzige Instanz, `signal.signal`, Browser öffnen, `session.json`). Das
  Programm lädt `transfer_core.py` und `ps5_streamer.py` aus der Datei und
  baut den Server wie `main()`: `ThreadingHTTPServer` mit `Handler`, eigene
  Sitzungsmarke, `Manager` auf dem Datenordner. Der Code des Werkzeugs bleibt
  unverändert; das Programm braucht von ihm `ThreadingHTTPServer`, `Handler`,
  `Manager`, `DEFAULTS`, `VERSION`, `validated_settings` und `atomic_json`.
- **Datenordner:** `DirectStream/` im Einstellungsordner des Programms
  (`state.json` mit Einstellungen und Warteschlange). Dort steht beim ersten
  Start die Adresse der PS5 und der FTP-Port aus den Einstellungen des
  Programms, wo noch keine Adresse gespeichert ist; eine gespeicherte Adresse
  wird nie überschrieben. Als Zielordner trägt das Programm `/data/homebrew`
  ein (ShadowMount+ durchsucht ihn immer; das Werkzeug selbst bringt
  `/data/ShadowMount` mit) – ebenfalls nur, solange keiner gespeichert ist.
  Die Strom-Einstellungen bleiben auf den Vorgaben des Werkzeugs (16 Ströme).
- **Typen der Oberfläche.** Das Werkzeug fragt `mimetypes`; unter Windows liest
  das die Registry, die `.js` und `.css` nicht immer richtig kennt – der
  Server schickt `nosniff`, ein falscher Typ ließe das Skript nicht laufen. Das
  Programm legt vor dem Start `.js`, `.css`, `.html` und `.svg` fest.
- Der Server läuft weiter, wenn man die Seite verlässt, und endet mit dem
  Programm. Läuft dann gerade ein Auftrag, fragt das Programm vorher.

## Nicht geprüft

Wie bei den Angaben des Werkzeugs selbst (`VALIDATION.md`, Abschnitt „Not
verified here“): Das Verhalten der FTP-Gegenseite an der Konsole – `SIZE`,
`REST`, `STOR`, Umbenennen, freier Platz – ist an der echten PS5 mit einer
kleinen Datei zu erproben, bevor große Titel übertragen werden.

## Aktualisieren

Ordner durch die neue Fassung ersetzen (neuer Ordnername mit Fassung),
`herkunft.json` neu erzeugen, `direct_stream.ORDNER` und die drei `.spec`
anpassen und `test_direct_stream.py` laufen lassen: Er hält die Importe des
Werkzeugs gegen die `hiddenimports` aller drei `.spec` und prüft, dass die vom
Programm benutzten Namen noch vorhanden sind.
