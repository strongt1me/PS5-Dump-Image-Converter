## Neu

- Umwandlung ohne Zwischenordner: Dump-Ordner und Abbilder werden direkt gelesen und das Ergebnis in einem Zug geschrieben, auch mit AMPR EMU, Backport, Fake-Signatur, DLC EMU und PlayGo.
- .ffpkg-Abbilder werden ohne UFS2Tool, Dokan und Administratorrechte gelesen und geschrieben.
- LZ4-Asset-Packs entstehen ebenfalls ohne Zwischenordner; mit AMPR EMU NG bleiben die gepackten Originale im Ergebnis weg.
- ABBILD BEARBEITEN › „Direkt ändern“: Dateien in .exfat, .ffpkg und .ffpfs lassen sich ohne Entpacken ändern; ein Journal macht einen Abbruch rückgängig.
- ZIP-Archive als Quelle werden bei Abbildern nicht mehr entpackt, und EINSTELLUNGEN › ARCHIV-PASSWÖRTER nimmt eine eigene Passwortliste für Archive auf.
- „Quelle nach Erfolg löschen“ (Haken, `--quelle-loeschen`) löscht die Quelle nach einem geprüften Lauf endgültig, nach Rückfrage.
- WEITERE TOOLS › „Geräte im Netz“ findet NAS und Rechner im Netz und setzt eine Windows-Freigabe als Quelle oder Ziel.
- Eine Stufenzeile zeigt die Dauer jedes Abschnitts, eine Vorabprüfung nennt alle Befunde im Spielordner vor dem Start, und der Ausgabename lässt sich per Vorlage bilden (`--ausgabename`).
- Eine Karte entfernt die Reste gescheiterter Läufe auf Wunsch, und eine Warnung meldet, wenn der Indexspeicher von AMPR EMU NG für ein Spiel voraussichtlich nicht reicht.
- Das Programm folgt beim Start der Anzeigesprache des Systems, und „Vollständige Prüfung“ gilt für zstd und LZ4.

## Geändert

- zstd packt mit allen Kernen und prüft standardmäßig per Stichprobe; zstd-Asset-Packs lassen Dateien lose, die AMPR EMU NG im Pack nicht fände.
- TEMP-ORDNER erscheint nur noch, wo ein Zwischenordner angelegt wird; KOMPRESSION (PFS) ist nur bei .ffpfsc bedienbar; „Y2JB Updater“ passt ohne Scrollen ins Fenster.

## Aktualisiert

- AMPR EMU NG 0.4.0-beta (Vorgabe für zstd-Asset-Packs), PS5Upload 12.4.12, PS5 Cooling & System Center – Pro 1.80.0, garlic-savemgr 1.15-beta23 und PS5-PKG-Tool 2.4.1.

## Behoben

- Eine andere AMPR-EMU-Fassung als NG lässt sich nicht mehr in ein zstd-gepacktes Spiel ohne Originale einbauen oder übertragen, und Backport lässt vorhandenes AMPR EMU liegen.
- Eine Quelle, die unter anderer Schreibung oder über eine Verknüpfung auch das Ziel ist, wird nicht mehr gelöscht oder als Rest angeboten.
- „Direkt ändern“ spielt ein Journal nicht zurück, das nicht zum Abbild gehört, und die Platzprüfung rechnet DLC-Ordner neben dem Spiel mit.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.98.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.98_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.98_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.98_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.97...v1.9.98
