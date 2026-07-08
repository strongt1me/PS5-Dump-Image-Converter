# Changelog

Diese Datei fasst die wichtigsten, heute noch nachvollziehbaren Aenderungen von v1.0.1 bis v1.7.80 in einfacher Sprache zusammen.

Hinweis:
Die ganz fruehen Zwischenversionen bis vor den spaeten 1.7.x-Releases sind im aktuellen Repository nicht mehr einzeln mit eigenen Release-Notizen erhalten. Deshalb sind die fruehen Schritte sauber zusammengefasst statt kuenstlich in viele Mini-Versionen aufgeteilt.

## v1.0.1 bis v1.7.75

In dieser langen Entwicklungsphase wurde das Projekt von einer fruehen Grundversion zu einem nutzbaren Windows-Tool fuer PS5-Dump-Workflows ausgebaut.

Wichtigste Aenderungen in dieser Phase:
- Start des Projekts und Aufbau der ersten Programmstruktur.
- Erste GUI fuer die wichtigsten PS5-Dump-Aufgaben.
- Grundfunktionen fuer Packen, Entpacken und Konvertieren wurden aufgebaut.
- Build-Skripte, Testdateien und Hilfswerkzeuge wurden schrittweise ergaenzt.
- Die Projektstruktur wurde bereinigt und Git-Ignorierregeln wurden erweitert.
- Signier-, Build- und Testablaeufe wurden vorbereitet und spaeter mehrfach vereinfacht.

Kurz gesagt:
Aus einer fruehen Basis entstand das eigentliche Desktop-Tool, auf dem die spaeteren 1.7.x-Versionen aufbauen.

## v1.7.76

Diese Version hat vor allem den Build-Ablauf sauberer und sicherer gemacht.

Neu oder verbessert:
- Das Build-Skript wurde bei der Passwortbehandlung fuer Signierung sicherer gemacht.
- Ueberfluessige oder fehlerhafte Build-Eintraege wurden entfernt.
- Kleine Fehler in den Build-Tests wurden bereinigt.
- Unnoetige PS5-Testdateien wurden besser aus Git herausgehalten.

Fuer normale Nutzer bedeutet das:
Der Build wurde stabiler und aufgeraeumter, ohne die eigentlichen Hauptfunktionen der App zu aendern.

## v1.7.77

Diese Version hat den Build- und Signierweg deutlich vereinfacht.

Neu oder verbessert:
- Abhaengigkeiten vom alten Signierablauf wurden entfernt.
- Zwang zu bestimmten Signierpfaden wurde abgebaut.
- Der Build-Start wurde einfacher und robuster gemacht.
- Die MIT-Lizenz-Registrierung und der allgemeine Build-Ablauf wurden besser abgestimmt.

Fuer normale Nutzer bedeutet das:
Die Erstellung der EXE wurde leichter wartbar und weniger fehleranfaellig.

## v1.7.78

Diese Version war vor allem ein technischer Umbau im Hintergrund.

Neu oder verbessert:
- Alte UFS2Tool-Altlasten wurden entfernt.
- Das Projekt wurde staerker auf die heute genutzten Wege reduziert.

Fuer normale Nutzer bedeutet das:
Weniger Altlasten im Code und ein klarerer, modernerer Unterbau.

## v1.7.79

Diese Version hat den Unterbau deutlich modernisiert und Aufgabe 7 erweitert.

Neu oder verbessert:
- Das MkPFS-Quellpaket wurde direkt eingebunden.
- Fuer Aufgabe 7 wurde die automatische Erzeugung von `ampr_emu.index` eingebaut.
- Das App-Icon fuer die Taskleiste wurde verbessert.
- Lokale Test- und Ausgabe-Dateien wurden besser aus Git herausgehalten.
- Aufgabe 1 wurde stabiler gemacht.
- Admin-Tests und optionale Imports wurden verbessert.
- Ein Benutzerhandbuch wurde ergaenzt.

Fuer normale Nutzer bedeutet das:
Mehr Stabilitaet, besseres Verhalten bei Aufgabe 7 und ein insgesamt modernerer Programmaufbau.

## v1.7.80

Diese Version war das grosse Feintuning- und Release-Update.

Neu oder verbessert:
- Aufgabe 7 unterstuetzt jetzt auch `.ffpkg` als Quelle.
- Aufgabe 7 schreibt bearbeitete `.ffpkg`-Quellen bewusst als `.ffpfsc` zurueck.
- `ampr_emu.index` wird jetzt bei Bedarf automatisch neu erzeugt.
- Vorschau und Infobox wurden in mehreren Aufgabenpfaden schneller und robuster gemacht.
- Die Fortschrittsanzeige wurde in mehreren Aufgaben deutlich verbessert.
- Aufgabe 1 wurde bei Abbruch, Neustart und Kompressionsanzeige stabiler.
- Aufgabe 2 erhielt bessere Fortschrittsstufen und schnellere Vorschaupfade.
- Aufgabe 3 zeigt ihren Abschluss und die Verifizierung klarer an.
- Aufgabe 4 behandelt Schrittgrenzen und Fortschritt sauberer.
- Fehlermeldungen und ETA-Anzeigen wurden vereinheitlicht und klarer gemacht.
- Der Live-Nachweis fuer Aufgabe 7 mit `.ffpkg` bestaetigt jetzt sichtbar `Rest:` und `ETA` im Hauptlauf und wird im E2E-Report mitprotokolliert.
- Die Windows-EXE bekam saubere Versionsinformationen.
- UPX wurde im Build deaktiviert, um False Positives bei Antivirus und SmartScreen eher zu reduzieren.
- README, Release Notes und Upload-Hinweise wurden ueberarbeitet.
- Credits wurden bereinigt und erweitert.
- Der Repository-Inhalt wurde aufgeraeumt.

Fuer normale Nutzer bedeutet das:
Die Version v1.7.80 ist die bisher rundeste und am besten dokumentierte Version. Sie bringt nicht nur neue Funktionen, sondern vor allem viele kleine Verbesserungen, die das Tool im Alltag verlaesslicher machen.

## Kurzfassung

- Fruehe Versionen: Grundfunktion des Tools aufgebaut.
- v1.7.76: Build und Tests sauberer gemacht.
- v1.7.77: Signier- und Build-Ablauf vereinfacht.
- v1.7.78: Alte Technik entfernt, Unterbau bereinigt.
- v1.7.79: MkPFS und Aufgabe 7 deutlich erweitert.
- v1.7.80: Grosse Komfort-, Stabilitaets- und Release-Verbesserung.