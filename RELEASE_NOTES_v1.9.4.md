## Behoben: Das Fenster blieb bei zwei Bildschirmen nicht, wo es war

Die in v1.9.3 eingeführte gemerkte Fenstergröße hatte einen Haken, der genau
die Leute traf, denen sie am meisten hilft: Wer zwei Monitore nutzt und das
Fenster auf dem zweiten stehen hatte, fand es beim nächsten Start auf dem
ersten wieder — jedes Mal.

**Woran es lag.** Das Programm fragte Windows nach der Bildschirmgröße und
bekam die des **ersten** Monitors. Ein Fenster, das weiter rechts stand, lag
nach dieser Rechnung außerhalb — und die Sicherung, die verlorene Fenster
zurückholen soll, holte es zurück, obwohl es gar nicht verloren war.

Jetzt zählt die gesamte Fläche über alle Bildschirme. Auch der Fall, dass der
zweite Monitor **links** vom ersten steht, ist abgedeckt; dann beginnt die
Fläche bei einem negativen Wert.

**Was gleich bleibt:** Wird ein Bildschirm abgezogen, rückt das Fenster
weiterhin auf den ersten zurück, statt unsichtbar im Nichts zu starten. Und
wer sein Fenster über beide Bildschirme zieht, behält diese Breite.

| Fall | Verhalten |
| --- | --- |
| Fenster auf dem zweiten Bildschirm | bleibt dort |
| zweiter Bildschirm links | bleibt dort |
| über beide Bildschirme gezogen | bleibt breit |
| Bildschirm abgezogen | rückt auf den ersten zurück |

## Aufgeräumt

Eine Methode ohne jeden Aufrufer ist entfernt — ein Überbleibsel der
Modulaufteilung, das nichts mehr tat.

Zwei weitere, die zunächst ebenfalls verdächtig aussahen, bleiben bewusst
stehen: Es sind Weiterleitungen, deren Verbleib eine Prüfung ausdrücklich
verlangt, und eine getestete Hilfsfunktion.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.9.4.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.9.4_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.9.4_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.9.4_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.9.4.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

Volle Testreihe grün — 1937 Prüfungen in 91 Dateien —, Anzeigediagnose ohne
Auffälligkeit, Umgebungsprüfung 15/0.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.3...v1.9.4
