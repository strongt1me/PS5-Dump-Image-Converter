# Changelog (English) – PS5 Dump & Image Converter

This English changelog starts with v2.0.0 and describes in plain language what changed for you as a user. The newest version is at the top. Earlier versions are listed in German in [CHANGELOG.md](CHANGELOG.md). Purely technical changes (for example to the build process or internal tests) are left out on purpose.

> **In short (v2.0.0):** The PKG / FPKG area now looks like tasks 1 to 6, builds packages with Dump Forge and shows the size of a game much faster.

---

## v2.0.1 – in progress

- **New:** The BACKPORT window has a “Firmware reference (check only)” field: you pick an unpacked firmware folder, and the program reports which functions are missing there – it copies nothing.
- **New:** The corrections for missing functions cover four more cases; a new checkbox adds a second kind of correction (experimental, off; measured on FW 12.00, not yet tried with a real backport).
- **Changed:** The “Backport needed” question recognises an already lowered game by its programs, not the param.json – for game folders, .ffpkg, .exfat, .ffpfs, .ffpfsc and .pkg, without unpacking.
- **New:** The KLOG window highlights the kernel message “Call to unpatched function” and points out that the game usually lacks a replacement library.
- **Changed:** In the BACKPORT window you only choose the firmware; backup, replacement libraries and compensation for missing functions always run by themselves, the checkboxes and fields are gone. The window is tidied up: the game name is large, Title ID and version are small pills, the automatic steps are green ticks, and the notes are down to one sentence each.
- **Changed:** The manual, FAQ, guides and README were checked against the program in five languages and corrected; “Task 7 – PKG / FPKG” now comes before “Task 8 – Validator” (chapters 12 and 13).
- **Updated:** AMPR EMU NG 0.5.0, now the default for zstd asset packs, and Kraken Mount 0.3.1; the index-memory warning knows NG 0.5.0.
- **Fixed:** When converting an already lowered image, the program sometimes still asked for a backport to firmware 12.
- **Fixed:** Several hints were out of date: the compression level (1 = fastest), the ShadowMount+ config.ini warning, what a backup is missing (only the content ID) and “zstd not yet measured on the console”.

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
