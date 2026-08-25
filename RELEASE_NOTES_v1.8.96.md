## Was ist neu

Diese Fassung räumt die Oberfläche auf: **63 sichtbare Ränder** sind
verschwunden, ohne dass etwas schlechter zu erkennen wäre.

* **Die Oberfläche ist randlos.** Um Karten, Eingabefelder, Listen und das
  Protokollfenster lagen dünne Linien. Sie unterbrachen das durchlaufende
  Hintergrundbild und liessen die Oberfläche unruhig wirken. Erhalten bleiben
  nur die drei **Farbfelder** im Design-Dialog — ohne Umrandung wäre nicht zu
  sehen, wo eine Farbe aufhört.
* **Eingabefelder bleiben erkennbar.** Ein Feld ohne Rand wäre unsichtbar,
  wenn es dieselbe Farbe hätte wie die Fläche darunter. Eingabefelder tragen
  deshalb jetzt eine eigene, leicht abgesetzte Füllung, die sich aus dem
  gewählten Design ableitet. Im hellen Design hob sich auch das
  Protokollfenster zu wenig ab; seine Farbe ist etwas kräftiger geworden.
* **Bedienung per Tastatur bleibt möglich.** Bisher zeigte ein Rahmen,
  welcher Knopf gerade dran ist. Statt des Rahmens ändert sich jetzt die
  **Fläche** des Bedienelements — auf dunklen Flächen heller, auf hellen
  dunkler, damit es in jedem Design sichtbar ist.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.96.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.96_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.96_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.96_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.96.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1484 Tests grün. Gefunden wurden die Ränder nicht durch eine Suche im
Quelltext, sondern durch einen Durchgang durch das laufende Fenster — fast
alle betroffenen Elemente haben gar keinen Namen, unter dem man hätte suchen
können. Zwei Ursachen kamen dabei heraus: Tk liefert Text-, Eingabe- und
Listenfelder von sich aus mit einem vertieften Rahmen aus, und weitere Ränder
steckten in Darstellungsvorlagen statt am Bedienelement.

Gegengeprüft wurde beides: dass kein Rand übrig ist (3 von 63, alle gewollt),
und dass ohne die Ränder nichts unsichtbar wird — Flächen und Fokusanzeige
sind in allen drei Designs nachgerechnet.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.95...v1.8.96
