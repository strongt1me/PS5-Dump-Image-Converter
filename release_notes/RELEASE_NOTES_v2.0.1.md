## New

- The corrections for missing functions cover four more cases and leave a function the firmware does have untouched (measured on FW 12.00, not yet tried with a real backport); title profiles still work as measured on the console.
- The KLOG window highlights the kernel message “Call to unpatched function” and points out that the game usually lacks a replacement library.
- Before a package is built, the program now says when Dump Forge would replace the game's AMPR runtime (even ampr-emu-ng) with its own, and names the way to keep it: an image from tasks 1 to 6, started with ShadowMount+.
- Four more payloads are bundled: NTFS Browser 1.4.0, NoUpdate 1.0.0, Linux Flasher 1.6.4 and PS5 Cleanup 1.3; the three with a web interface appear in the payload table under CONSOLE.
- Before a package is built, the log also names a damaged picture in sce_sys when the source is an image (.ffpkg, .exfat, .ffpfs, .ffpfsc), not only a game folder.

## Changed

- The “Backport needed” question recognises an already lowered game by its programs, not the param.json – for game folders, .ffpkg, .exfat, .ffpfs, .ffpfsc and .pkg, without unpacking.
- With AMPR EMU and an LZ4 asset pack, the TEMP FOLDER field now appears only when it is already clear before the start that the run needs an intermediate folder (a pack profile of the user next to the game folder, a title profile with several groups) – no longer for every game.
- In the BACKPORT window you only choose the firmware; backup, replacement libraries and compensation for missing functions always run by themselves, the checkboxes and fields are gone.
- The BACKPORT window is tidied up: the game name is large, Title ID and version are small pills, the automatic steps are green ticks, and the notes are down to one sentence each.
- An unusable custom target value in the settings file no longer blocks BACKPORT – the log names it, and the value from the firmware table applies; a firmware reference from the settings file now also applies in the BACKPORT window.
- The manual, FAQ, guides and README were checked against the program in five languages and corrected; “Task 7 – PKG / FPKG” now comes before “Task 8 – Validator” (chapters 12 and 13).
- The Updates button no longer asks GitHub about DPI v2 (its project has no releases), so a full check stays below the limit of 60 requests per hour.

## Updated

- AMPR EMU NG 0.5.0, now the default for zstd asset packs, and Kraken Mount 0.3.1; the index-memory warning knows NG 0.5.0.
- Dump Forge 0.5.7 (console ELF and command line), elfldr 0.28, WebKit Autoloader 0.8.4 (0.8.2 and 0.8.3 are included as a choice too) and YT-Blocker 1.4r6.
- garlic-savemgr 2.0, PS5Upload 12.6.24 and PS5 Cooling & System Center – Pro 1.92.0.

## Fixed

- When converting an already lowered image, the program sometimes still asked for a backport to firmware 12.
- The manual said Dump Forge takes `fakelib` over into a package unchanged; for games with AMPR EMU it puts its own runtime there, and the log line for package builds now says so too.
- Several hints were out of date: the compression level (1 = fastest), the ShadowMount+ config.ini warning, what a backup is missing (only the content ID) and “zstd not yet measured on the console”.
- The bundled pack profiles for ASTRO BOT and EA Sports UFC 6 never applied to real PS5 dumps, because the program looked for the title ID only in the param.sfo, which PS5 dumps do not have; it now also reads the param.json.
- In the BACKPORT window, text in the file table was cut off at display sizes from 125 % (the “Kind” column, at 200 % also file names and status); the columns now grow with it, the SDK number is centred, and the warning sentence wraps at the window width.
- BACKPORT counts failed corrections in its error count, and closing the window while the corrections run brings the cancel message instead of “Done”.
- A game folder whose BACKPORT was cancelled after the eboot.bin counted as “already lowered”; the modules in sce_module now count too.
- After a BACKPORT to firmware 4 to 6, some games stopped right at the start with “Failed to create the heap”: the adjusted libc passed the older firmware a flag it does not know. BACKPORT now adjusts these places too (measured with GTA V on FW 4.03).
- When Dump Forge converts a .pkg straight into an image, the report now names the exchange of the AMPR runtime; a “BACKPORT needed” that rests on the param.json alone now says so.
- Deliberately damaged packages and images can no longer hold up the source check for minutes or make it end with an error.
- In the English, Spanish, French and Italian manuals and in the FAQ, examples showed German or English placeholders such as `<PS5-Adresse>`; they are now in the language of the document.
- When a folder is copied from the console, a file name with a backslash or “..” can no longer lead outside the target folder, and a broken transfer no longer leaves a cut file under its final name.
- If the PC drive runs full while a single file is fetched from the console, the transfer is still read to the end, so ftpsrv on the console stays usable.
- Closing the program while an archive is being unpacked as the source now asks first, stops 7-Zip and removes the half-unpacked folder.
- config.ini and profiles.ini of ShadowMount+, autoload.txt and the KLOG payload on USB are written through a temporary file, so a broken connection never leaves a half file on the console.
- The Updates button no longer stores the WebKit Autoloader host (.exe/.py) without a checksum, and a tool with several files is stored completely or not at all.
- “Edit image” keeps an undo journal that cannot be read (as .undo.defekt) and warns that the image may be half written, and it no longer saves over an undo journal that is still pending.
- After converting from “Edit image”, the main window gets its target format back; on exFAT images with clusters below 4 KiB, saving no longer writes into neighbouring clusters.
- A pasted PS5 update address whose file name contains a backslash or “..” is refused.
- PS4 PKG Dump & Image Converter no longer lays an update that is not newer than the chosen base game over it, and a second update with the same version is named in the log instead of being dropped silently.
- PS4 PKG Dump & Image Converter: a licence-only DLC without game data no longer stops the run; a failed or cancelled run removes its half package or half image (.partial), and a time limit is reported as such.
- When base game and update are merged into one PS4 package, the space check now also counts the finished package on the same drive.
- The game info no longer reads a whole PS5 .pkg into memory to find its update address.

## Removed

- The older OnionHEN 0.0.13 is no longer included; only OnionHEN 0.9.0 is bundled.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v2.0.1.exe` (needs administrator rights at startup).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v2.0.1_linux_x86_64` – make it executable with `chmod +x` after downloading.
- **macOS:** `PS5_Dump_Image_Converter_v2.0.1_macos_arm64.dmg` (Apple Silicon) and `PS5_Dump_Image_Converter_v2.0.1_macos_x86_64.dmg` (Intel). If macOS says “The developer cannot be verified” at the first start, section 20.3 of the user manual helps.

**Full Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v2.0.0...v2.0.1

<details>
<summary>Deutsch (German)</summary>

## Neu

- Die Korrekturen für fehlende Funktionen decken vier weitere Fälle ab und lassen eine Funktion, die die Firmware doch hat, unangetastet (an FW 12.00 gemessen, noch ohne echten Backport erprobt); Titelprofile wirken weiter wie an der Konsole gemessen.
- Das KLOG-Fenster hebt die Kernel-Meldung „Call to unpatched function“ farbig hervor und weist darauf hin, dass dem Spiel meist eine Ersatzbibliothek fehlt.
- Vor dem Bau eines Pakets sagt das Programm jetzt, wenn Dump Forge die AMPR-Laufzeit des Spiels (auch ampr-emu-ng) durch seine eigene ersetzt, und nennt den Weg, sie zu behalten: ein Abbild aus den Aufgaben 1 bis 6, das ShadowMount+ startet.
- Vier weitere Payloads liegen bei: NTFS Browser 1.4.0, NoUpdate 1.0.0, Linux Flasher 1.6.4 und PS5 Cleanup 1.3; die drei mit Weboberfläche stehen unter KONSOLE in der Payload-Tabelle.
- Vor dem Bau eines Pakets nennt das Protokoll ein beschädigtes Bild in sce_sys auch, wenn die Quelle ein Abbild ist (.ffpkg, .exfat, .ffpfs, .ffpfsc), nicht nur bei einem Spielordner.

## Geändert

- Die Rückfrage „Backport nötig“ erkennt ein schon herabgesetztes Spiel an seinen Programmen statt an der param.json – bei Spielordnern, .ffpkg, .exfat, .ffpfs, .ffpfsc und .pkg, ohne zu entpacken.
- Das Feld TEMP-ORDNER erscheint bei AMPR EMU mit LZ4-Asset-Pack nur noch, wenn schon vor dem Start feststeht, dass der Lauf einen Zwischenordner braucht (Packprofil des Anwenders neben dem Spielordner, Titelprofil mit mehreren Gruppen) – nicht mehr bei jedem Spiel.
- Im BACKPORT-Fenster gibst du nur noch die Firmware an; Sicherung, Ersatzbibliotheken und der Ausgleich fehlender Funktionen laufen immer von selbst, die Haken und Felder entfallen.
- Das BACKPORT-Fenster ist aufgeräumt: Spielname groß, Title-ID und Version als kleine Pillen, die automatischen Schritte als grüne Haken, die Hinweise auf je einen Satz.
- Ein unbrauchbarer eigener Zielwert aus der Einstellungsdatei sperrt BACKPORT nicht mehr – das Protokoll nennt ihn, und es gilt der Wert der Firmware-Tabelle; eine Firmware-Referenz aus der Einstellungsdatei gilt jetzt auch im BACKPORT-Fenster.
- Handbuch, FAQ, Anleitungen und README wurden in fünf Sprachen gegen das Programm geprüft und berichtigt; „Aufgabe 7 – PKG / FPKG“ steht jetzt vor „Aufgabe 8 – Validator“ (Kapitel 12 und 13).
- Der Knopf „Updates“ fragt GitHub nicht mehr nach DPI v2 (das Projekt hat keine Freigaben) – eine volle Prüfung bleibt so unter der Grenze von 60 Anfragen je Stunde.

## Aktualisiert

- AMPR EMU NG 0.5.0, die jetzt die Vorgabe für zstd-Asset-Packs ist, und Kraken Mount 0.3.1; die Warnung zum Indexspeicher kennt NG 0.5.0.
- Dump Forge 0.5.7 (Konsolen-ELF und Befehlszeile), elfldr 0.28, WebKit Autoloader 0.8.4 (0.8.2 und 0.8.3 liegen zur Auswahl mit bei) und YT-Blocker 1.4r6.
- garlic-savemgr 2.0, PS5Upload 12.6.24 und PS5 Cooling & System Center – Pro 1.92.0.

## Behoben

- Beim Umwandeln eines schon herabgesetzten Abbilds fragte das Programm manchmal trotzdem nach einem Backport für Firmware 12.
- Das Handbuch sagte, Dump Forge übernehme `fakelib` unverändert ins Paket; bei Spielen mit AMPR EMU setzt es dort seine eigene Laufzeit ein, und die Protokollzeile zum Paketbau sagt es jetzt auch.
- Mehrere Hinweise stimmten nicht mehr: die Kompressionsstufe (1 statt 3 = am schnellsten), die config.ini-Warnung zu ShadowMount+, was einem Backup fehlt (nur die Content-ID) und „zstd an der Konsole noch nicht gemessen“.
- Die mitgelieferten Packprofile für ASTRO BOT und EA Sports UFC 6 griffen bei echten PS5-Dumps nie, weil das Programm die Title-ID nur in der param.sfo suchte, die PS5-Dumps nicht haben; jetzt liest es auch die param.json.
- Im BACKPORT-Fenster wurde bei Anzeigegrößen ab 125 % Text in der Dateitabelle abgeschnitten (Spalte „Art“, bei 200 % auch Dateinamen und Status); die Spalten wachsen jetzt mit, die SDK-Zahl steht mittig, und der Warnsatz bricht nach der Fensterbreite um.
- BACKPORT zählt gescheiterte Korrekturen in der Fehlerzahl mit, und wer das Fenster während der Korrekturen schließt, bekommt die Abbruchmeldung statt „Fertig“.
- Ein Spielordner, bei dem ein BACKPORT nach der eboot.bin abgebrochen wurde, galt als „schon herabgesetzt“; jetzt zählen auch die Module in sce_module.
- Nach einem BACKPORT für Firmware 4 bis 6 brachen manche Spiele gleich beim Start mit „Failed to create the heap“ ab: Die angepasste libc übergab der älteren Firmware ein Flag, das sie nicht kennt. BACKPORT passt diese Stellen jetzt mit an (an GTA V auf FW 4.03 gemessen).
- Wandelt Dump Forge ein .pkg direkt in ein Abbild, nennt der Bericht jetzt den Austausch der AMPR-Laufzeit; ein „BACKPORT nötig“, das nur auf der param.json beruht, sagt das jetzt dazu.
- Gezielt beschädigte Pakete und Abbilder können die Prüfung der Quelle nicht mehr minutenlang aufhalten oder mit einem Fehler abbrechen.
- Im englischen, spanischen, französischen und italienischen Handbuch und in der FAQ standen in Beispielen deutsche oder englische Platzhalter wie `<PS5-Adresse>`; sie stehen jetzt in der Sprache des Dokuments.
- Beim Holen eines Ordners von der Konsole kann ein Dateiname mit Rückstrich oder „..“ nicht mehr aus dem Zielordner führen, und eine abgebrochene Übertragung lässt keine gekürzte Datei unter ihrem Endnamen zurück.
- Läuft beim Holen einer einzelnen Datei von der Konsole der PC-Datenträger voll, wird die Übertragung trotzdem zu Ende gelesen – ftpsrv auf der Konsole bleibt bedienbar.
- Wer das Programm schließt, während ein Archiv als Quelle entpackt wird, wird jetzt gefragt; 7-Zip wird angehalten und der halbe Entpackordner weggeräumt.
- config.ini und profiles.ini von ShadowMount+, autoload.txt und das KLOG-Payload auf USB werden über eine Zwischendatei geschrieben – ein Verbindungsabriss hinterlässt auf der Konsole nie eine halbe Datei.
- Der Knopf „Updates“ legt den Host des WebKit Autoloaders (.exe/.py) nie ohne Prüfsumme ab, und ein Werkzeug aus mehreren Dateien kommt ganz oder gar nicht an seinen Platz.
- „Abbild bearbeiten“ legt ein nicht lesbares Rückgängig-Journal beiseite (.undo.defekt) und warnt, dass das Abbild halb geschrieben sein kann; über ein noch offenes Journal wird nicht mehr gespeichert.
- Nach dem Umwandeln aus „Abbild bearbeiten“ hat das Hauptfenster sein Zielformat wieder; bei exFAT-Abbildern mit Clustern unter 4 KiB schreibt das Speichern nicht mehr in Nachbarcluster.
- Eine eingefügte PS5-Update-Adresse mit Rückstrich oder „..“ im Dateinamen wird abgewiesen.
- „PS4 PKG Dump & Image Converter“ legt ein Update, das nicht neuer als das gewählte Basisspiel ist, nicht mehr darüber, und ein zweites Update gleicher Fassung wird im Protokoll genannt, statt still wegzufallen.
- „PS4 PKG Dump & Image Converter“: Ein reines Lizenz-DLC ohne Spieldaten hält den Lauf nicht mehr auf; ein gescheiterter oder abgebrochener Lauf räumt sein halbes Paket bzw. Abbild (.partial) weg, und eine Zeitgrenze wird als solche gemeldet.
- Beim Zusammenführen von Basisspiel und Update zu einem PS4-Paket zählt die Platzprüfung jetzt auch das fertige Paket auf demselben Laufwerk.
- Die Spiel-Info liest ein PS5-.pkg nicht mehr ganz in den Speicher, um seine Update-Adresse zu finden.

## Entfernt

- Die ältere OnionHEN 0.0.13 liegt nicht mehr bei; mitgeliefert wird nur noch OnionHEN 0.9.0.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v2.0.1.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v2.0.1_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v2.0.1_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v2.0.1_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 20.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v2.0.0...v2.0.1

</details>
