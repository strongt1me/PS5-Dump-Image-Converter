## Neu

- Auf der Seite PKG stehen Cover und Titel des markierten Spiels in der Seitenleiste, und „Spiel Info – Updates & Patches“ zeigt seine Angaben samt Updates von orbispatches.com.
- PS4Mount 0.4.4 (gasb07) liegt bei und steht in „Konsole & Payloads“ (Port 8770) – es spielt PS4-Fake-PKGs direkt vom USB-Laufwerk, ohne sie zu installieren.
- Bei Aufgabe 1 wählt der Knopf „Archiv…“ neben „Dump Ordner“ ein .zip, .7z oder .rar; die Zwischenfrage „Ordner oder Archiv“ entfällt.
- Archive mit Passwort werden entpackt – das Programm probiert „pippo“ und „DLPSGAME.COM“ und fragt sonst nach dem Passwort.

## Geändert

- Der AMPR-Mitschnitt-Assistent ist von WEITERE TOOLS in die Ansicht KONSOLE umgezogen (Knopf „10. AMPR-Mitschnitt“) und beginnt erst mit STARTEN.
- Die gewählte Zeile der Seitenleiste hat leicht runde Ecken, und die Knopfreihe steht etwa 5 mm unter dem Umschalter UMWANDELN/KONSOLE.
- Auf der Seite FPKG läuft der Fortschritt nur noch vorwärts und zeigt unter den Knöpfen Datei, Menge, Dateizahl und Zeit; das Protokoll steht in Worten, mit Abstand zwischen den Meldungen.
- Die Seite PKG / FPKG hat keine Überschrift mehr, die Knöpfe PKG und FPKG sind größer und stehen bündig über der Karte QUELLE.

## Aktualisiert

- Payload Manager 0.6.0; das Senden über ihn (wenn Port 9021 zu ist) ist an die neue Fassung angepasst.

## Behoben

- FPKG → .ffpkg scheiterte bei knappem Platz auf C: erst nach dem Entpacken; jetzt prüft das Programm vorher mit der echten Größe und baut das Abbild bei Bedarf auf dem Ziellaufwerk.
- Kleine Auswahlfenster gingen in der Ecke oben links auf; sie stehen jetzt dort, wo geklickt wurde.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.77.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.77_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.77_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.77_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.
- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.77.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.75...v1.9.77
