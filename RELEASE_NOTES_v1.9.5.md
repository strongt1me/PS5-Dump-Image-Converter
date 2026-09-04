## Behoben: Minimiert heruntergefahren, und das Fenster war verstellt

Wer das Programm maximiert nutzte, es in die Taskleiste legte und dann den
Rechner herunterfuhr, fand es beim nächsten Start **nicht** maximiert vor —
sondern als fast bildschirmfüllendes Fenster mit sonderbarem Versatz.

**Woran es lag.** Ein minimiertes Fenster meldet dem Programm nicht
„maximiert“, sondern „minimiert“. Beim Merken zählte allein die Frage, ob es
maximiert sei — und die war dann verneint. Gespeichert wurde daraufhin die
volle Bildschirmgröße als gewöhnliche Fenstergröße: genau der Wert, den das
Programm an dieser Stelle eigentlich vermeidet.

Jetzt läuft der letzte Zustand mit, in dem das Fenster **nicht** minimiert
war. Beim Schließen zählt dieser, wenn das Fenster gerade in der Taskleiste
liegt.

**Wen es betraf.** Über die Taskleiste geschlossen trat der Fehler nie auf —
dort stellt Windows das Fenster vorher wieder her. Der Weg dorthin war
**Herunterfahren oder Abmelden** bei minimiertem Programm. Wer die
Einstellung „Rechner nach erfolgreichem Abschluss herunterfahren“ nutzt,
konnte darauf stoßen.

| Weg | vorher | jetzt |
| --- | --- | --- |
| maximiert → minimiert → heruntergefahren | startet unmaximiert, versetzt | startet maximiert |
| verkleinert → minimiert → heruntergefahren | Größe ging verloren | Größe kommt zurück |
| über die Taskleiste geschlossen | war schon richtig | unverändert |

Der Fehler stammt aus v1.9.3 und war in v1.9.4 enthalten.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.5.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.5_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.5_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.5_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.5.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün, Anzeigediagnose ohne Auffälligkeit, Umgebungsprüfung
15 geprüft / 0 Fehler. Neun neue Prüfungen decken den minimierten Fall ab.
Gegen die Vorversion gehalten schreibt dieselbe Messung dort noch die volle
Bildschirmgröße in die Einstellungsdatei — die Prüfungen beschreiben also
wirklich den Fehler und nicht bloß das neue Verhalten.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.4...v1.9.5
