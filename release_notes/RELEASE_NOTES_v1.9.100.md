## Neu

- PKG / FPKG sieht aus wie die Aufgaben 1 bis 6 (Einbau-Karte, Prüfung der Quelle, Fortschritt), und Pakete baut allein Dump Forge – aus Spielordnern und Abbildern, ohne Zwischenordner.
- Aus einem Spiel mit LZ4- oder zstd-Packs entsteht ein FPKG, weil Dump Forge die Packs beim Bau entpackt; ein PS4-Paket aus einem gepackten Dump-Ordner lehnt das Programm ab.
- Ein gewähltes Spiel erscheint auf PKG / FPKG sofort, die Größe wird danach deutlich schneller gezählt als bisher, und bei nicht lesbaren Ordnern steht „mind. X“ statt „unbekannt“.
- AMPR EMU, DLC EMU und PlayGo fragen vor dem Lauf nach, wenn das Spiel sie braucht und nicht mitbringt; eine weitere Frage erscheint, wenn es mehr Firmware verlangt, als die Konsole hat.
- Die Haken PlayGo und DLC setzt das Programm beim Wählen eines Spiels selbst, und die Seitenleiste zeigt den SDK-Stand, wenn die Firmware nicht in der param.json steht.
- Bei Archiven als Quelle zeigt das Programm den TEMP-ORDNER, fragt vor dem Entpacken wohin, rechnet die Platzprüfung mit der entpackten Größe, und EINSTELLUNGEN hat den Eintrag ARBEITSORDNER (TEMP).
- Im Asset-Pack-Fenster baut der Knopf PACKEN zstd-Packs direkt in einen fertigen Spielordner.
- Enthält ein Spielordner Verknüpfungen, Junctions oder andere Reparsepunkte, die Dump Forge ablehnt, warnt das Protokoll vor dem Start, und die Ablehnung steht in der Sprache des Fensters.

## Geändert

- Aufklapplisten sind so breit wie ihr längster Eintrag, „Asset-Pack“ steht in Aufgabe 1 bei jeder Skalierung ganz im Feld, und der Fortschrittsbalken der Knopfleiste hat runde Ecken.
- Die Kurzinfo bleibt im Bildschirm, und die automatische NG-Suche zeigt ihren Stand in den Einstellungen.

## Aktualisiert

- Dump Forge 0.5.6 (Konsolen-ELF und Befehlszeile), Kraken Mount 0.3.0, PS4Mount 0.8.0, NeoEnabler 0.7.0 und garlic-worker 1.6.6.
- PS5Upload 12.6.11, PS5 Cooling & System Center – Pro 1.88.0, ProsperoMgr 1.2.1, MemDBG 20261112 und PatchDL 0.3.13.

## Behoben

- Ein fertiges Paket bleibt erhalten, wenn das Ablegen scheitert, und STARTEN bleibt nicht gesperrt, wenn ein Spiel während der Prüfung aus der Liste genommen wird.
- Die Prüfung der Quelle setzt die Haken zuverlässig, auch wenn sie bei einer langsamen Quelle länger dauert, und ein Wechsel der Aufgabe lässt keine fremden Haken stehen.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.100.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.100_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.100_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.100_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 20.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.99...v1.9.100
