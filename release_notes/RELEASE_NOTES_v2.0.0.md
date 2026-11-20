## New

- PKG / FPKG looks like tasks 1 to 6 (add-ons, source check, progress), and Dump Forge alone builds packages – from game folders and images, without an intermediate folder.
- A game with LZ4 or zstd packs becomes an FPKG because Dump Forge unpacks the packs during the build; a PS4 package from a packed dump folder is refused.
- A chosen game appears on PKG / FPKG immediately, its size is counted afterwards and much faster than before, and unreadable folders show “at least X” instead of “unknown”.
- AMPR EMU, DLC EMU and PlayGo ask before the run if the game needs them and does not bring them; one more question appears if the game demands more firmware than the console has.
- The program sets the PlayGo and DLC checkboxes itself when you choose a game, and the sidebar shows the SDK level when the firmware is not in the param.json.
- For archives as a source, the program shows the TEMP FOLDER, asks where to unpack first, counts the unpacked size in the space check, and SETTINGS gets a WORKING FOLDER (TEMP) entry.
- In the Asset Pack window, the PACK button builds zstd packs directly into a finished game folder.
- If a game folder contains links, junctions or other reparse points that Dump Forge refuses, the log warns before the start, and the refusal appears in the language of the window.

## Changed

- Drop-down lists are as wide as their longest entry, “Asset Pack” fits completely in the field of task 1 at every scaling, and the progress bar of the button row has rounded corners.
- The tooltip stays on the screen, and the automatic NG search shows its status in the settings.

## Updated

- Dump Forge 0.5.6 (console ELF and command line), Kraken Mount 0.3.0, PS4Mount 0.8.0, NeoEnabler 0.7.0 and garlic-worker 1.6.6.
- PS5Upload 12.6.11, PS5 Cooling & System Center – Pro 1.88.0, ProsperoMgr 1.2.1, MemDBG 20261112 and PatchDL 0.3.13.

## Fixed

- A finished package is kept when saving it fails, and START no longer stays locked when a game is removed from the list during the check.
- The source check sets the checkboxes reliably even when a slow source makes it take longer, and switching the task no longer leaves foreign checkboxes behind.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v2.0.0.exe` (needs administrator rights at startup).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v2.0.0_linux_x86_64` – make it executable with `chmod +x` after downloading.
- **macOS:** `PS5_Dump_Image_Converter_v2.0.0_macos_arm64.dmg` (Apple Silicon) and `PS5_Dump_Image_Converter_v2.0.0_macos_x86_64.dmg` (Intel). If macOS says “The developer cannot be verified” at the first start, section 20.3 of the user manual helps.

**Full Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.99...v2.0.0

<details>
<summary>Deutsch (German)</summary>

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

- **Windows:** `PS5_Dump_Image_Converter_v2.0.0.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v2.0.0_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v2.0.0_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v2.0.0_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 20.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.99...v2.0.0

</details>
