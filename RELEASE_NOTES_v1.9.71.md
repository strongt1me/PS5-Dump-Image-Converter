## Neu

- Unter WEITERE TOOLS gibt es „PS5 PKG Dump & Image Converter“: PS5-Pakete (Debug-Pakete) prüfen, entpacken und zu .ffpfsc, .ffpfs, exFAT oder .ffpkg umwandeln, mit Bibliothek, Cover und technischer Übersicht – und aus einem Spielordner ein Debug-Paket bauen.
- Der Knopf „Updates“ auf „Konsole & Payloads“ prüft alle mitgelieferten Werkzeuge auf neuere Fassungen und bietet sie zum Herunterladen an.
- Auf „Konsole & Payloads“ legst du per Stern Favoriten fest, die das Programm beim Start und mit „Favoriten senden“ an die PS5 schickt (Port 9021 wird bei Bedarf zuerst geöffnet); ersetzt „Grundausstattung starten“.
- Die Titelleisten aller Fenster sind unter Windows 11 dunkel graublau; im Design Hell bleiben sie hell. Die Knöpfe der Seitenleiste haben jetzt die Farbe der Knöpfe im rechten Bereich.
- Im PS5 PKG Dump & Image Converter schickt die Aktion „Auf die PS5 entpacken“ ein Paket beim Lesen gleich per FTP an die Konsole – ohne entpackte Kopie auf dem PC und mit Fortsetzen nach einem Abbruch.
- Vier Knöpfe (Schnell, Ausgewogen, Maximal, Wenig RAM) setzen Kompressionsstufe und Kernzahl mit einem Klick; die Blockgröße bleibt unverändert.
- Aufgabe 1 nimmt auch ein Archiv (.zip, .7z oder .rar) mit dem Spielordner als Quelle; es wird in den Arbeitsordner entpackt, 7-Zip für .7z und .rar liegt bei.
- Geht beim Packen der Arbeitsspeicher aus, startet das Programm den Lauf selbst mit halb so vielen Kernen neu, bis zu dreimal.

## Geändert

- Beim Öffnen des Programms ist im Bereich UMWANDELN nichts angekreuzt (AMPR EMU, PlayGo, BACKPORT), AMPR EMU steht auf Normal mit der neuesten Fassung ohne Pack, und Quelle, Ziel- und Temp-Ordner sind leer; ein leerer Temp-Ordner heißt Windows-Temp.
- Die Live-Anzeige während eines Laufs nennt jetzt den freien Arbeitsspeicher und warnt unter 1 GB.
- Beim Senden eines Ordners an die Konsole fragt das Programm bei einem vorhandenen Ziel, ob es fortsetzen soll, und baut eine abgerissene Verbindung neu auf.
- Auf der Seite „WebKit Autoloader“ stehen die drei Wege in einer Reihe, über jedem Knopf sein Symbol (deutsch und englisch).
- Das Banner von psxtools.de erscheint jetzt zwei Minuten nach dem Start, steht fünf Minuten und kommt danach alle 30 Minuten wieder; es folgt dem Fenster, ein Rechtsklick schließt es.
- Das Umschalten zwischen den Ansichten und Aufgaben geht spürbar schneller, weil unveränderte runde Flächen nicht mehr neu gezeichnet werden.

## Aktualisiert

- Das Fenster CREDITS dankt jetzt auch nexgen999, matem6 und Phoenixx.
- PKG Manager 1.5.1, WebKit Autoloader 0.6.1 (zur Auswahl neben den älteren), PS5Upload 7.0.22, AnyPad PS5 0.9.1-beta, PS5 Cooling & System Center 1.61.0, CheatRunner 0.18, WK-AutoLoader 1.1.1 und ShadowMount+ 1.7beta5fix1.
- Die Warnung vor Titeln ohne fakelib erkennt jetzt auch die neuen Einträge „fakelib_mode“ und „fakelib_default_mode“ von ShadowMount+ 1.7beta5 und nennt den auslösenden Eintrag.

## Behoben

- PS5Upload wird an seinem Port 9120 erkannt (bisher war 9113 eingetragen).
- In der Ansicht KONSOLE leuchten die Seitenknöpfe beim Darüberfahren wieder auf, wie in der Ansicht UMWANDELN.
- Der Strich unter „OK“ erscheint in Meldungsfenstern nicht mehr beim Öffnen, sondern nur noch bei Bedienung mit der Tab-Taste.
- Das Abbrechen im PS4 PKG Dump & Image Converter hing fest, weil nur der äußere Prozess beendet wurde. Jetzt endet alles sofort, der Abbruch wird angezeigt und der Arbeitsordner im Hintergrund entfernt.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.71.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.71_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.71_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.71_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.
- **Prüfsummen:** `SOURCE_FILE_MANIFEST_v1.9.71.sha256` listet die SHA-256 aller Quelldateien dieser Fassung.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.69...v1.9.71
