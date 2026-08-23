## Was ist neu

Diese Fassung behebt einen Fehler, der die Funktion **PS4 PKG → ffpfsc** nach
dem ersten Backup unbrauchbar machte, sowie drei Befunde aus einem echten
Diagnosebericht.

* **Das zweite PKG-Backup zeigte die Spiele des ersten.** Und danach ließ sich
  gar keines mehr einlesen – auch das erste nicht, das eben noch ging. Das
  Werkzeug verwendete sein Spieleverzeichnis wieder, ohne zu prüfen, ob es zur
  neuen Quelle gehört. Da alle Quellen denselben Arbeitsordner benutzen, traf
  das immer zu. Alte Arbeitsordner müssen nicht von Hand aufgeräumt werden.
* **Ein Fenster nahm dem Hauptfenster das Mausrad.** Wer einmal über
  *Einstellungen* oder *Design-Einstellungen* fuhr, konnte den Hauptinhalt bis
  zum Neustart nicht mehr rollen.
* **Die Protokolldatei wuchs ungebremst** – auf 22 MB. Sie rollt jetzt bei
  4 MB um und behält drei ältere. Testläufe schreiben nicht mehr hinein; sie
  waren der Grund für Zeilen im Bericht, die siebzehnmal dasselbe sagten und
  nach einem Fehler aussahen.
* **Der Diagnosebericht meldet nur noch Echtes.** „requests: fehlt" stand
  darin, obwohl das Programm diese Bibliothek nirgends benutzt; dasselbe galt
  für `paramiko`. Dafür steht jetzt die Größe der Protokolldatei im Bericht.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.93.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.93_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.93_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.93_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.93.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1334 Tests grün, davon vierzehn neu. Der PKG-Fehler ist an nachgestellten
Beständen belegt – gleiche Quelle wird weiterbenutzt, andere Quelle löst einen
frischen Durchlauf aus. Der Mausrad-Fehler wurde am laufenden Programm
gemessen: vorher tot, jetzt nutzbar.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.92...v1.8.93
