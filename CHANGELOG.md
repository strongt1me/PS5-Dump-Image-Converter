# Changelog

Diese Datei fasst die wichtigsten, heute noch nachvollziehbaren Änderungen von v1.0.1 bis v1.7.80 in einfacher Sprache zusammen.

Hinweis:
Die ganz frühen Zwischenversionen bis vor den späten 1.7.x-Releases sind im aktuellen Repository nicht mehr einzeln mit eigenen Release-Notizen erhalten. Deshalb sind die frühen Schritte sauber zusammengefasst statt künstlich in viele Mini-Versionen aufgeteilt.

## v1.0.1 bis v1.7.75

In dieser langen Entwicklungsphase wurde das Projekt von einer frühen Grundversion zu einem nutzbaren Windows-Tool für PS5-Dump-Workflows ausgebaut.

Wichtigste Änderungen in dieser Phase:
- Start des Projekts und Aufbau der ersten Programmstruktur.
- Erste GUI für die wichtigsten PS5-Dump-Aufgaben.
- Grundfunktionen für Packen, Entpacken und Konvertieren wurden aufgebaut.
- Build-Skripte, Testdateien und Hilfswerkzeuge wurden schrittweise ergänzt.
- Die Projektstruktur wurde bereinigt und Git-Ignorierregeln wurden erweitert.
- Signier-, Build- und Testabläufe wurden vorbereitet und später mehrfach vereinfacht.

Kurz gesagt:
Aus einer frühen Basis entstand das eigentliche Desktop-Tool, auf dem die späteren 1.7.x-Versionen aufbauen.

## v1.7.76

Diese Version hat vor allem den Build-Ablauf sauberer und sicherer gemacht.

Neu oder verbessert:
- Das Build-Skript wurde bei der Passwortbehandlung für Signierung sicherer gemacht.
- Überflüssige oder fehlerhafte Build-Einträge wurden entfernt.
- Kleine Fehler in den Build-Tests wurden bereinigt.
- Unnötige PS5-Testdateien wurden besser aus Git herausgehalten.

Für normale Nutzer bedeutet das:
Der Build wurde stabiler und aufgeräumter, ohne die eigentlichen Hauptfunktionen der App zu ändern.

## v1.7.77

Diese Version hat den Build- und Signierweg deutlich vereinfacht.

Neu oder verbessert:
- Abhängigkeiten vom alten Signierablauf wurden entfernt.
- Zwang zu bestimmten Signierpfaden wurde abgebaut.
- Der Build-Start wurde einfacher und robuster gemacht.
- Die MIT-Lizenz-Registrierung und der allgemeine Build-Ablauf wurden besser abgestimmt.

Für normale Nutzer bedeutet das:
Die Erstellung der EXE wurde leichter wartbar und weniger fehleranfällig.

## v1.7.78

Diese Version war vor allem ein technischer Umbau im Hintergrund.

Neu oder verbessert:
- Alte UFS2Tool-Altlasten wurden entfernt.
- Das Projekt wurde stärker auf die heute genutzten Wege reduziert.

Für normale Nutzer bedeutet das:
Weniger Altlasten im Code und ein klarerer, modernerer Unterbau.

## v1.7.79

Diese Version hat den Unterbau deutlich modernisiert und Aufgabe 7 erweitert.

Neu oder verbessert:
- Das MkPFS-Quellpaket wurde direkt eingebunden.
- Für Aufgabe 7 wurde die automatische Erzeugung von `ampr_emu.index` eingebaut.
- Das App-Icon für die Taskleiste wurde verbessert.
- Lokale Test- und Ausgabe-Dateien wurden besser aus Git herausgehalten.
- Aufgabe 1 wurde stabiler gemacht.
- Admin-Tests und optionale Imports wurden verbessert.
- Ein Benutzerhandbuch wurde ergänzt.

Für normale Nutzer bedeutet das:
Mehr Stabilität, besseres Verhalten bei Aufgabe 7 und ein insgesamt modernerer Programmaufbau.

## v1.7.80

Diese Version war das große Feintuning- und Release-Update.

Neu oder verbessert:
- Aufgabe 7 unterstützt jetzt auch `.ffpkg` als Quelle.
- Aufgabe 7 schreibt bearbeitete `.ffpkg`-Quellen bewusst als `.ffpfsc` zurück.
- `ampr_emu.index` wird jetzt bei Bedarf automatisch neu erzeugt.
- Vorschau und Infobox wurden in mehreren Aufgabenpfaden schneller und robuster gemacht.
- Die Fortschrittsanzeige wurde in mehreren Aufgaben deutlich verbessert.
- Aufgabe 1 wurde bei Abbruch, Neustart und Kompressionsanzeige stabiler.
- Aufgabe 2 erhielt bessere Fortschrittsstufen und schnellere Vorschaupfade.
- Aufgabe 3 zeigt ihren Abschluss und die Verifizierung klarer an.
- Aufgabe 4 behandelt Schrittgrenzen und Fortschritt sauberer.
- Fehlermeldungen und ETA-Anzeigen wurden vereinheitlicht und klarer gemacht.
- Der Live-Nachweis für Aufgabe 7 mit `.ffpkg` bestätigt jetzt sichtbar `Rest:` und `ETA` im Hauptlauf und wird im E2E-Report mitprotokolliert.
- Die Windows-EXE bekam saubere Versionsinformationen.
- UPX wurde im Build deaktiviert, um False Positives bei Antivirus und SmartScreen eher zu reduzieren.
- README, Release Notes und Upload-Hinweise wurden überarbeitet.
- Credits wurden bereinigt und erweitert.
- Der Repository-Inhalt wurde aufgeräumt.

Für normale Nutzer bedeutet das:
Die Version v1.7.80 ist die bisher rundeste und am besten dokumentierte Version. Sie bringt nicht nur neue Funktionen, sondern vor allem viele kleine Verbesserungen, die das Tool im Alltag verlässlicher machen.

## Kurzfassung

- Frühe Versionen: Grundfunktion des Tools aufgebaut.
- v1.7.76: Build und Tests sauberer gemacht.
- v1.7.77: Signier- und Build-Ablauf vereinfacht.
- v1.7.78: Alte Technik entfernt, Unterbau bereinigt.
- v1.7.79: MkPFS und Aufgabe 7 deutlich erweitert.
- v1.7.80: Große Komfort-, Stabilitäts- und Release-Verbesserung.