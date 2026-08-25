## Was ist neu

Diese Fassung macht die Fortschrittsanzeige verlässlich und legt eine
Umgebungsprüfung bei, die die häufigen „läuft bei mir nicht“-Ursachen in
Sekunden benennt.

* **Der Balken kann nicht mehr stehenbleiben.** In seltenen Fällen fror die
  gesamte Anzeige ein – Balken, Prozentzahl und Statuszeile –, ohne Meldung und
  ohne Absturz; die Aufgabe lief im Hintergrund weiter, war aber nicht mehr zu
  verfolgen. Die Anzeigerechnung verträgt jetzt jeden Wert, der bei ihr
  ankommt, und bleibt immer innerhalb der Skala.
* **Sammelkonvertierung: eine durchgehende Anzeige.** Bisher lief der Balken
  für jede Datei von vorn los; der Sprung auf 0 % sah aus, als beginne alles
  neu. Jede Datei bekommt jetzt ihren Abschnitt – bei zwei Dateien 0–50 % und
  50–100 %. Rückwärts läuft der Balken nie mehr. Steht die Anzeige länger als
  fünf Sekunden still, erscheint eine mitlaufende Uhr.
* **Neu: `--doktor`.** Prüft lange Pfade (abgeschaltet lassen sie Pakete mit
  tiefen Ordnern abbrechen – oft mit einer Meldung, die nach etwas anderem
  klingt), das Dateisystem der Ordner (auf FAT32 endet jede Datei bei 4 GB),
  Schreibrecht und Platz, widersprüchliche Paketstände, ob sich die
  mitgelieferten Programme starten lassen, und ob die Einstellungsdatei lesbar
  ist. Rückgabewert 1 bei einem echten Fehler. Dieselben Angaben stehen im
  Fenster **DIAGNOSE** im Abschnitt *Doktor*. Die Eingabeaufforderung muss als
  Administrator geöffnet sein – das Programm verlangt die Rechte für jeden
  Aufruf.
* **Der Diagnosebericht wurde um zwei Abschnitte erweitert.** *Optimierung*
  vergleicht den Durchsatz der letzten Aufgabe mit dem besten je gemessenen
  Lauf derselben Kompressionsstufe – wird eine Aufgabe deutlich langsamer,
  steht das jetzt im Bericht. *Eigenschaften* prüft beim Erstellen des Berichts
  nach, ob Anzeigerechnung und Spieldaten-Leser sich regelgerecht verhalten.
* **AMPR EMU und PlayGo liegen neben dem Programm** statt darin, im Ordner
  **PlayGo & AMPR_EMU** – wie die Hintergrundbilder. Neue Versionen lassen sich
  hineinlegen, ohne auf ein Programm-Update zu warten. Beim Entpacken des
  Bündels ist der Ordner mitzukopieren.

## Downloads

| Plattform | Datei |
| --- | --- |
| Windows | `PS5_Dump_Image_Converter_v1.8.94.exe` |
| Linux | `PS5_Dump_Image_Converter_v1.8.94_linux_x86_64` |
| macOS (Apple Silicon) | `PS5_Dump_Image_Converter_v1.8.94_macos_arm64.dmg` |
| macOS (Intel) | `PS5_Dump_Image_Converter_v1.8.94_macos_x86_64.dmg` |

Prüfsummen aller Quelldateien: `SOURCE_FILE_MANIFEST_v1.8.94.sha256`

## Hinweis

Nur für **eigene, rechtmäßig erworbene** Inhalte. Das Umgehen technischer
Schutzmaßnahmen und die Verbreitung urheberrechtlich geschützter Inhalte sind
nicht Zweck dieses Projekts. Nutzung auf eigene Verantwortung; keine Verbindung
zu Sony Interactive Entertainment. Einzelheiten im
[Haftungsausschluss](https://github.com/strongt1me/PS5-Dump-Image-Converter#haftungsausschluss).

## Geprüft

1444 Tests grün, davon 110 neu. Der Anzeigefehler wurde nicht abgeleitet,
sondern gefunden: Eigenschaftsbasiertes Testen suchte selbst nach einer
Eingabe, die die Anzeige zum Stehen bringt, und fand sie im ersten Anlauf.

Dass die Tests um die Fortschrittsrechnung etwas taugen, ist gemessen und
nicht behauptet – ein Mutationstest verändert die Rechnung an zwanzig Stellen,
und jede einzelne Änderung lässt mindestens einen Test fehlschlagen.

**Vollständiges Changelog:** https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.8.93...v1.8.94
