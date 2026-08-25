## Was ist neu

Eine Korrektur zu v1.8.94: Das Programm ist wieder **eine einzige Datei**.

* **AMPR EMU und PlayGo stecken wieder im Programm.** Seit v1.8.94 lagen sie in
  einem Ordner daneben, damit sich eine neue AMPR-Fassung hineinlegen lässt,
  ohne auf ein Update zu warten. Der Preis war zu hoch: Wer das Programm
  weitergibt, verschiebt oder aus dem Download-Ordner heraus startet und den
  Ordner dabei vergisst, hat in **Aufgabe 7** keine einzige Version zur
  Auswahl – wortlos, mit der Meldung „keine passende Datei“, ohne erkennbare
  Ursache. Beim Entpacken des Bündels ist jetzt nichts mehr mitzukopieren.
  Die Programmdatei wächst dadurch um rund 1 MB.
* **Eigene AMPR-Fassungen bleiben möglich.** Der AMPR-EMU-Manager hat eine
  eigene Ordnerwahl; auf der Kommandozeile leistet `--ampr-store` dasselbe.
* **`--doktor` meldete auf Linux und macOS Fehler, die keine waren.** Die
  Startprobe der mitgelieferten Programme hielt dort auch Dateien für
  Programme, die keine sind – etwa eine Lizenzdatei – und meldete dafür einen
  Fehler. Entschieden wird jetzt am Dateiformat statt am Dateirecht.

Alles aus v1.8.94 bleibt: die durchgehende Fortschrittsanzeige in der
Sammelkonvertierung, der Balken, der nicht mehr stehenbleiben kann, und die
Umgebungsprüfung im Fenster **DIAGNOSE** wie auf der Kommandozeile.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.95.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.95_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.95_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.95_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.95.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1460 Tests grün. An der fertigen Programmdatei nachgemessen statt angenommen:
25 AMPR-/PlayGo-Einträge und 40 Hintergrundbilder liegen im Archiv, und neben
der Datei liegt nichts mehr. Die Umgebungsprüfung findet beides.

Die Tests zu dieser Stelle wurden nicht gelöscht, sondern umgedreht – samt der
Gegenprobe, dass ein danebenliegender Ordner aus einem früheren Bau **nicht**
gewinnt. Sonst arbeitete das Programm still mit einem Stand, den niemand mehr
pflegt.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.94...v1.8.95
