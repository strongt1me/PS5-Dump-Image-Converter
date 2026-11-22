# Changelog (English) – PS5 Dump & Image Converter

This English changelog starts with v2.0.0 and describes in plain language what changed for you as a user. The newest version is at the top. Earlier versions are listed in German in [CHANGELOG.md](CHANGELOG.md). Purely technical changes (for example to the build process or internal tests) are left out on purpose.

> **In short (v2.0.0):** The PKG / FPKG area now looks like tasks 1 to 6, builds packages with Dump Forge and shows the size of a game much faster.

---

## v2.0.1 – in progress

- **New:** The corrections for missing functions cover four more cases and leave a function the firmware does have untouched (measured on FW 12.00, not yet tried with a real backport); title profiles still work as measured on the console.
- **Changed:** The “Backport needed” question recognises an already lowered game by its programs, not the param.json – for game folders, .ffpkg, .exfat, .ffpfs, .ffpfsc and .pkg, without unpacking.
- **New:** The KLOG window highlights the kernel message “Call to unpatched function” and points out that the game usually lacks a replacement library.
- **New:** Before a package is built, the program now says when Dump Forge would replace the game's AMPR runtime (even ampr-emu-ng) with its own, and names the way to keep it: an image from tasks 1 to 6, started with ShadowMount+.
- **Changed:** With AMPR EMU and an LZ4 asset pack, the TEMP FOLDER field now appears only when it is already clear before the start that the run needs an intermediate folder (a pack profile of the user next to the game folder, a title profile with several groups) – no longer for every game.
- **Changed:** In the BACKPORT window you only choose the firmware; backup, replacement libraries and compensation for missing functions always run by themselves, the checkboxes and fields are gone.
- **Changed:** The BACKPORT window is tidied up: the game name is large, Title ID and version are small pills, the automatic steps are green ticks, and the notes are down to one sentence each.
- **Changed:** An unusable custom target value in the settings file no longer blocks BACKPORT – the log names it, and the value from the firmware table applies; a firmware reference from the settings file now also applies in the BACKPORT window.
- **Changed:** The manual, FAQ, guides and README were checked against the program in five languages and corrected; “Task 7 – PKG / FPKG” now comes before “Task 8 – Validator” (chapters 12 and 13).
- **Updated:** AMPR EMU NG 0.5.0, now the default for zstd asset packs, and Kraken Mount 0.3.1; the index-memory warning knows NG 0.5.0.
- **Updated:** Dump Forge 0.5.7 (console ELF and command line), elfldr 0.28, WebKit Autoloader 0.8.3 (0.8.2 is included as a choice too) and YT-Blocker 1.4r6.
- **Updated:** garlic-savemgr 2.0, PS5Upload 12.6.22 and PS5 Cooling & System Center – Pro 1.91.0.
- **Fixed:** When converting an already lowered image, the program sometimes still asked for a backport to firmware 12.
- **Fixed:** The manual said Dump Forge takes `fakelib` over into a package unchanged; for games with AMPR EMU it puts its own runtime there, and the log line for package builds now says so too.
- **Fixed:** Several hints were out of date: the compression level (1 = fastest), the ShadowMount+ config.ini warning, what a backup is missing (only the content ID) and “zstd not yet measured on the console”.
- **Fixed:** The bundled pack profiles for ASTRO BOT and EA Sports UFC 6 never applied to real PS5 dumps, because the program looked for the title ID only in the param.sfo, which PS5 dumps do not have; it now also reads the param.json.
- **Fixed:** In the BACKPORT window, text in the file table was cut off at display sizes from 125 % (the “Kind” column, at 200 % also file names and status); the columns now grow with it, the SDK number is centred, and the warning sentence wraps at the window width.
- **Fixed:** BACKPORT counts failed corrections in its error count, and closing the window while the corrections run brings the cancel message instead of “Done”.
- **Fixed:** A game folder whose BACKPORT was cancelled after the eboot.bin counted as “already lowered”; the modules in sce_module now count too.
- **Fixed:** When Dump Forge converts a .pkg straight into an image, the report now names the exchange of the AMPR runtime; a “BACKPORT needed” that rests on the param.json alone now says so.
- **Fixed:** Deliberately damaged packages and images can no longer hold up the source check for minutes or make it end with an error.
- **Fixed:** In the English, Spanish, French and Italian manuals and in the FAQ, examples showed German or English placeholders such as `<PS5-Adresse>`; they are now in the language of the document.

---

## v2.0.0 – 2026-11-19

- **New:** PKG / FPKG looks like tasks 1 to 6 (add-ons, source check, progress), and Dump Forge alone builds packages – from game folders and images, without an intermediate folder.
- **New:** A game with LZ4 or zstd packs becomes an FPKG because Dump Forge unpacks the packs during the build; a PS4 package from a packed dump folder is refused.
- **New:** A chosen game appears on PKG / FPKG immediately, its size is counted afterwards and much faster than before, and unreadable folders show “at least X” instead of “unknown”.
- **New:** AMPR EMU, DLC EMU and PlayGo ask before the run if the game needs them and does not bring them; one more question appears if the game demands more firmware than the console has.
- **New:** The program sets the PlayGo and DLC checkboxes itself when you choose a game, and the sidebar shows the SDK level when the firmware is not in the param.json.
- **New:** For archives as a source, the program shows the TEMP FOLDER, asks where to unpack first, counts the unpacked size in the space check, and SETTINGS gets a WORKING FOLDER (TEMP) entry.
- **New:** In the Asset Pack window, the PACK button builds zstd packs directly into a finished game folder.
- **New:** If a game folder contains links, junctions or other reparse points that Dump Forge refuses, the log warns before the start, and the refusal appears in the language of the window.
- **Changed:** Drop-down lists are as wide as their longest entry, “Asset Pack” fits completely in the field of task 1 at every scaling, and the progress bar of the button row has rounded corners.
- **Changed:** The tooltip stays on the screen, and the automatic NG search shows its status in the settings.
- **Updated:** Dump Forge 0.5.6 (console ELF and command line), Kraken Mount 0.3.0, PS4Mount 0.8.0, NeoEnabler 0.7.0 and garlic-worker 1.6.6.
- **Updated:** PS5Upload 12.6.11, PS5 Cooling & System Center – Pro 1.88.0, ProsperoMgr 1.2.1, MemDBG 20261112 and PatchDL 0.3.13.
- **Fixed:** A finished package is kept when saving it fails, and START no longer stays locked when a game is removed from the list during the check.
- **Fixed:** The source check sets the checkboxes reliably even when a slow source makes it take longer, and switching the task no longer leaves foreign checkboxes behind.
