## Geändert

- Dateien mit der Endung .ini (etwa die dlc_emu.ini) bleiben beim Packen eines Asset-Packs lose und damit von Hand änderbar, bei zstd und bei LZ4.
- Packen und Prüfen eines zstd-Asset-Packs lesen die Dateien jetzt in großen Blöcken im Voraus; das Packen ist dadurch schneller, und die Prüfung läuft auf Festplatten mit weniger Kopfsprüngen.

- Ordner-Umwandlungen packen mit bis zu 8 statt 4 Fäden; die Prüfung „Schnell“ liest zusätzlich eine Stichprobe der Blöcke (etwa 1 %), „Vollständig“ liest weiter alles, „Aus“ prüft nur den Aufbau.

## Behoben

- Ein fremder Spielordner mit manipuliertem zstd-Index kann beim Entpacken keine Dateien mehr außerhalb des Zielordners anlegen oder löschen.
- Bricht eine Sicherung (`.orig`) oder ein exFAT-Bau mitten im Schreiben ab, bleibt keine halbe Datei unter dem Endnamen liegen; ein vorhandenes Ergebnis bleibt bis zum Schluss unberührt.
- Ein gebautes exFAT-Abbild, das sich nicht lesen lässt, gilt nicht mehr als fertig; ein nicht lesbarer Ordner beim Entpacken einer .ffpkg oder eines Asset-Packs wird gemeldet statt still ausgelassen.
- Die Einrichtung für AMPR EMU meldet bei ShadowMount+ 1.7beta12 nicht mehr bei jedem Lauf eine Abweichung bei `on`/`1`; der Wechsel eines Abbilds von rw auf ro im INI-Editor behält seinen `mount_mode`.
- Ein unvollständig verschobener Dump-Ordner (Aufgabe 4) trägt die Endung `.unvollstaendig`; ein abgebrochener Download wird beim nächsten Start abgeschlossen statt mit „HTTP 416“ zu scheitern.
- Installer für OSFMount, Dokan und FileZilla liegen in einem privaten Ordner; eine bei der Laufwerkssuche gefundene `filezilla.exe` startet erst nach Rückfrage; die PS4-Updateabfrage folgt nur Adressen bei Sony; beim Entpacken von Archiven bleibt Platz auf dem Laufwerk frei.
- ABBRECHEN beendet auch eine Engine, die gerade in einem langen Abschnitt steckt, nach einem sofortigen Neustart zuverlässig; die Rückfragen beim Überschreiben nennen jetzt, dass das vorhandene Ergebnis vor dem Bau gelöscht wird.

## Aktualisiert

- AMPR EMU NG 0.3.5 (ein neues Spiel über einem vorhandenen Spielstand hängt nicht mehr im Ladebildschirm; die Laufzeit läuft flüssiger). Davor 0.3.4: die Laufzeit passt ihre Threads dem Spiel an und behebt Schwarzbild und Hänger bei Crimson Desert.
- PS5Upload 12.4.8, Web File Manager 1.14, garlic-savemgr 1.15-beta22, garlic-worker 1.5.4 und PS5 Cooling & System Center – Pro 1.79.0.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.96.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.96_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.96_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.96_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.95...v1.9.96
