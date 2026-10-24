## Neu

- Hat ein Spiel PlayGo-Inhalte und ist PlayGo nicht angehakt, fragt das Programm vorab, ob es eingeschaltet werden soll – wie bei DLC EMU, auch ohne AMPR EMU.

## Geändert

- Die param.json-Prüfung meldet fehlende optionale Felder (conceptId, gameIntent, originContentVersion), den Wert `upgradable` und ein niedrigeres targetContentVersion nur noch als Hinweis; Ukrainisch (uk-UA) gilt als bekannter Sprachcode.
- Die Haken unter der Pfad-Karte stehen zweispaltig nebeneinander, solange die Karte breit genug ist.

## Behoben

- Der Haken „Ergebnis nach erfolgreichem Abschluss an PS5 senden“ war von einem anderen Haken verdeckt; PlayGo allein ohne AMPR EMU wird jetzt tatsächlich eingebaut.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.87.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.87_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.87_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.87_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.86...v1.9.87
