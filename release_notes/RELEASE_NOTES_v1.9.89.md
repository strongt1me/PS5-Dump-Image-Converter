## Neu

- Ziehen und Ablegen in die Felder Quelle, Ziel und Temp funktioniert auch, wenn das Programm als Administrator läuft; leere Felder zeigen einen grauen Hinweis, was man hineinziehen kann.
- Die Backport-Funktion wurde optimiert und verbessert: Der Backport lässt sich im Spiel integrieren oder separat als Ordner erstellen, der im Dump-Ordner des Spiels ausgetauscht wird (auch an die Konsole senden).
- Die Bibliothek zeigt die verlangte Firmware, liest `.ffpkg` ohne Einhängen und zeigt Update-Pakete (Delta) mit Titel und IDs.

## Geändert

- Die Pfad-Karte springt nicht mehr, BAUFORM steht direkt unter dem Formathinweis, die Knöpfe in Aufgabe 7 heißen „PS4 PKG“ und „PS5 PKG“, und große runde Flächen rechnen viel schneller (der erste Wechsel zu PS5 PKG erscheint sofort).

## Aktualisiert

- ShadowMount+ 1.7beta10, zftpd 1.7.0, PS5Upload 9.1.0, PS4Mount 0.7.2, PatchDL 0.3.11, NeoEnabler 0.5.3, WebKit Autoloader 0.6.2, ps5-unified-autoloader 0.1.7 und ps5-ultrapack 2.3.3.

## Behoben

- Gleichzeitiges Lesen von Abbild-Angaben in der Bibliothek konnte die Lesefunktion der Engine dauerhaft ersetzt zurücklassen, sodass sie nur noch einen Teil des Verzeichnisbaums las.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.89.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.89_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.89_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.89_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.88...v1.9.89
