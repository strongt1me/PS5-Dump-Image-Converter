## Geändert

- Dateien mit der Endung .ini (etwa die dlc_emu.ini) bleiben beim Packen eines Asset-Packs lose und damit von Hand änderbar, bei zstd und bei LZ4.
- Packen und Prüfen eines zstd-Asset-Packs lesen die Dateien jetzt in großen Blöcken im Voraus; das Packen ist dadurch schneller, und die Prüfung läuft auf Festplatten mit weniger Kopfsprüngen.

## Aktualisiert

- AMPR EMU NG 0.3.4 (die Laufzeit passt ihre Threads dem Spiel an; behebt Schwarzbild und Hänger bei Crimson Desert).
- PS5Upload 12.4.4, Web File Manager 1.14, garlic-savemgr 1.15-beta21, garlic-worker 1.5.4 und PS5 Cooling & System Center – Pro 1.79.0.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.96.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.96_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.96_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.96_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.95...v1.9.96
