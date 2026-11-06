## Neu

- Archive (.zip, .7z, .rar) lassen sich direkt als Quelle wählen – in Aufgabe 1, in der Sammelkonvertierung, in Aufgabe 5 und auf der Kommandozeile (`--archiv-passwort`); das Programm entpackt sie selbst und räumt danach auf.
- WEITERE TOOLS › ABBILD BEARBEITEN entpackt ein Abbild (.ffpfsc, .ffpfs, .ffpkg, .exFAT), lässt Dateien ersetzen, umbenennen, löschen oder hinzufügen und speichert das Ergebnis als neues Abbild `<Name>_bearbeitet`; das Original bleibt unberührt.
- Asset-Packs lassen sich auch mit zstd statt LZ4 packen (nur für AMPR EMU NG); eigene TOML-Regeln (`_ampr_pack.toml` neben dem Dump oder als feste Regeldatei in den Einstellungen, auch mit `include_from` und `exclude_from`) bestimmen, was gepackt wird.
- Benutzerhandbuch, die drei Anleitungen, FAQ und README gibt es auch auf Englisch, Spanisch, Italienisch und Französisch; die Knöpfe öffnen die Fassung der Oberflächensprache (maschinell übersetzt, nicht von Muttersprachlern geprüft).

## Geändert

- Die Anleitung zur neuen fakelib-Methode von ShadowMount+ ist mit 1.7beta11 abgeglichen (Log-Zeilen, Meldungen, `fakelib_mode`, `libkernel.sprx`).

## Aktualisiert

- AMPR EMU NG 0.3.2 (läuft jetzt auch Resonance: A Plague Tale Legacy als voll gepackte Installation; 0.3.1: Days Gone Remastered und Sonic x Shadow Generations).
- zlib-ng 1.1.0 für MkPFS; auf Stufe 9 entstehen in einzelnen Blöcken andere Bytes, die PS5 liest sie im Test unverändert.
- PS5Upload 11.2.4, PS4Mount 0.7.3 und PS5 Cooling & System Center – Pro 1.76.9.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.91.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.91_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.91_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.91_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.90...v1.9.91
