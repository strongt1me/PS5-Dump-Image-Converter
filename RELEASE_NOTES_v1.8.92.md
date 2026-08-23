## Was ist neu

* **Ein Drehknopf statt der alten Spinbox.** Die Worker-Zahl wird jetzt an
  einem Ring eingestellt. Für genaue Werte bleibt alles erhalten: Mausrad und
  Pfeiltasten ändern um eins, ein Doppelklick springt zur Voreinstellung
  zurück, und die Zahl steht groß in der Mitte.
* **Die AMPR-Spieleauswahl zeigt Spielnamen.** Statt `CUSA00775 (CUSA00775)`
  steht dort jetzt der Name des Spiels, die Kennung bleibt in Klammern. Die
  Namen kommen von der Konsole, nicht aus dem Netz.
* **Fehler im Lesen der `param.sfo` behoben.** Der Dateikopf trägt vier
  Felder; gelesen wurden alle vier, aber um eines versetzt zugeordnet. Als
  „Anzahl der Einträge" kam dadurch eine Adresse heraus, der Leser lief über
  das Dateiende hinaus und lieferte gar nichts. Deshalb blieb das Feld immer
  leer. Betrifft jede Stelle, die Angaben aus einer `param.sfo` zeigt.
* **Das Auswahlfenster ist auf JS-Loader-Größe gebracht** und hat einen
  Rollbalken; das Mausrad rollt ebenfalls. Bei vielen Spielen bleiben die
  Knöpfe unten damit erreichbar.
* **Online-Nachschlag nur noch auf dem Mac gesperrt.** Unter Windows und Linux
  schlägt das Programm fehlende Angaben wieder von sich aus nach. Das ist
  jeweils nur die Werkseinstellung – eine selbst getroffene Wahl gilt auf
  jedem System weiter.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.92.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.92_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.92_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.92_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.92.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1320 Tests grün. Neu darunter sind zehn Prüfungen für den Drehknopf – Grenzen,
Mausrad, Pfeiltasten, Doppelklick und die Zahl in der Mitte – sowie sechs für
den Online-Nachschlag, die festhalten, dass eine selbst getroffene Einstellung
die Werkseinstellung jedes Systems schlägt.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.91...v1.8.92
