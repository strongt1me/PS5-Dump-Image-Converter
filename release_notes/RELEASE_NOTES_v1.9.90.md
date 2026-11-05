## Neu

- Die PKG/FPKG-Seite ist im Stil von Aufgabe 1 aufgebaut und erkennt PS4- und PS5-Pakete von selbst.
- AMPR EMU NG 0.3.0 (stille und Debug-Fassung); die NG-Fassungen stehen in allen Listen direkt unter der neuesten Fassung 0.4.2.1.
- Die Betriebsprüfung im Diagnosebericht nennt liegen gebliebene OSFMount- und UFS2-Laufwerke samt Befehl zum Aushängen.
- BACKPORT „Fehlende Funktionen neutralisieren“ (Haken, aus, ohne Garantie): Aufrufe, die die Zielfirmware nicht kennt, liefern einen leeren Rückgabewert, statt das Spiel abstürzen zu lassen.
- BACKPORT „Korrekturprofil des Spiels anwenden“ (Haken, aus, ohne Garantie): geprüfte Byte-Korrekturen je Titel und Fassung; mitgeliefert ist ein Profil für Anno 117 auf Firmware 4.xx.

## Geändert

- Die Bereiche PS4 PKG und PS5 PKG passen ohne Rollen ins Fenster, das Zielformat zeigt nur noch die Endung (.ffpkg, .ffpfsc, .ffpfs, .exFAT, .pkg), und der Block „Ausgewähltes Paket“ ist weg.

## Aktualisiert

- ShadowMount+ 1.7beta11, PS5Upload 11.0.8, PS5 Cooling & System Center – Pro 1.76.7, NeoEnabler 0.6.2, Web File Manager 1.13-rc2, PatchDL 0.3.12, CheatRunner 0.18.1, garlic-worker und das PS5-PKG-Tool 0.0.3.

## Behoben

- Updates von Sony auf exFAT-Laufwerken beginnen sofort zu laden, statt beim Vorbereiten der Datei stundenlang stillzustehen; das Fenster zeigt, wann es mit dem Server verbindet.
- ABBRECHEN im Ladefenster für Updates wirkt sofort, beim Einlesen eines PS5-PKG öffnen sich keine schwarzen Konsolenfenster mehr, und die PKG/FPKG-Seite steht beim ersten Klick gleich richtig.
- ABBRECHEN stoppt die Umwandlung in den Aufgaben 1 bis 6 jetzt wirklich – bisher lief die Engine weiter, und nach „Abgebrochen“ erschien eine fertige Datei; halb entpackte Dump-Ordner werden entfernt.
- Eine leere, falsch benannte oder abgeschnittene .exfat/.ffpkg wird vor dem Start abgewiesen, statt „erfolgreich“ in ein kleines, unbrauchbares Ergebnis verwandelt zu werden.
- Aufgabe 8 meldet beschädigte Blöcke einer .ffpfsc (Entpackprüfung) und eine falsche Prüfsumme der exFAT-Boot-Region jetzt als beschädigt statt als Hinweis.
- Aufgabe 2 bietet für eine .ffpfs wieder .ffpfsc an, die Kommandozeile hängt bei Rückfragen nicht mehr, und das Entpacken einer .ffpkg versucht bei einem abgewiesenen Laufwerksbuchstaben den nächsten freien.
- Das Laufwerk einer .ffpkg wird beim Entpacken, Abbrechen und Prüfen sauber ausgehängt und bleibt nicht mehr im Explorer stehen; Vorschau, Entpacken und Prüfung hängen die Datei nacheinander ein, nicht mehr gleichzeitig.
- Die Sammelkonvertierung nennt bei schon vorhandenen Zielen den richtigen Grund, und die Texte des AMPR EMU Managers nennen ihn wieder beim Namen statt „Aufgabe 7“.
- BACKPORT meldete Funktionen aus Bibliotheken, die die Firmware-Tabelle gar nicht führt, fälschlich als fehlend.
- Das Senden von PS4-Paketen an die Konsole (Remote Package Installer) gibt die Paketdatei beim Beenden sofort frei, statt sie noch kurz gesperrt zu halten.

## Downloads

- **Windows:** `PS5_Dump_Image_Converter_v1.9.90.exe` (benötigt Administratorrechte beim Start).
- **Linux (x86-64):** `PS5_Dump_Image_Converter_v1.9.90_linux_x86_64` – nach dem Download mit `chmod +x` ausführbar machen.
- **macOS:** `PS5_Dump_Image_Converter_v1.9.90_macos_arm64.dmg` (Apple Silicon) und `PS5_Dump_Image_Converter_v1.9.90_macos_x86_64.dmg` (Intel). Meldet macOS beim ersten Start „Der Entwickler kann nicht überprüft werden“, hilft Abschnitt 19.3 im Benutzerhandbuch.

**Vollständiges Changelog**: https://github.com/strongt1me/PS5-Dump-Image-Converter/compare/v1.9.89...v1.9.90
